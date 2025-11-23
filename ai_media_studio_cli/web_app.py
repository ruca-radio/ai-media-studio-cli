"""
Web UI for AI Media Studio CLI
FastAPI backend that wraps the CLI functionality
"""
import asyncio
import os
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from google import genai
from google.genai.types import GenerateVideosConfig, Video
from dotenv import load_dotenv

from .model_manager import model_manager
from .models_config import get_model_config
from . import download

load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="AI Media Studio Web UI",
    description="Web interface for AI Media Studio CLI - Generate videos, images, and music with Google's AI models",
    version="2.0.0"
)

# CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Google GenAI client (lazily to avoid requiring credentials at import time)
_client = None

def get_client():
    """Get or create the GenAI client"""
    global _client
    if _client is None:
        _client = genai.Client()
    return _client

# In-memory storage for jobs (in production, use Redis or a database)
jobs: Dict[str, Dict[str, Any]] = {}


class AspectRatio(str, Enum):
    """Video aspect ratios"""
    widescreen = "16:9"
    portrait = "9:16"


class Resolution(str, Enum):
    """Video resolutions"""
    hd_720 = "720"
    full_hd_1080 = "1080"


class GenerateVideoRequest(BaseModel):
    """Request model for video generation"""
    prompt: str = Field(..., description="Video generation prompt")
    model: str = Field("veo-001", description="Video generation model ID")
    aspect_ratio: str = Field("16:9", description="Video aspect ratio")
    resolution: str = Field("1080", description="Video resolution")
    number_of_videos: int = Field(1, ge=1, le=4, description="Number of videos to generate")
    duration_seconds: int = Field(8, description="Video duration in seconds")
    enhance_prompt: bool = Field(True, description="Enable AI prompt enhancement")


class JobStatus(str, Enum):
    """Job status enum"""
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobResponse(BaseModel):
    """Response model for job status"""
    job_id: str
    status: JobStatus
    progress: int = Field(0, ge=0, le=100)
    message: str = ""
    videos: List[str] = []
    error: Optional[str] = None
    created_at: str
    updated_at: str


class ModelInfo(BaseModel):
    """Model information"""
    id: str
    name: str
    description: str
    max_videos: int
    max_duration: int
    resolutions: List[str]
    capabilities: Dict[str, Any]


def get_default_gcs_uri() -> str:
    """Get the default GCS URI from environment variables."""
    bucket_name = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET")
    bucket_path = os.getenv("GOOGLE_CLOUD_STORAGE_PATH", "videos")

    if not bucket_name:
        raise ValueError(
            "GOOGLE_CLOUD_STORAGE_BUCKET environment variable is required. "
            "Please add it to your .env file."
        )

    bucket_path = bucket_path.lstrip("/")
    return f"gs://{bucket_name}/{bucket_path}"


async def generate_video_task(job_id: str, request: GenerateVideoRequest):
    """Background task for video generation"""
    try:
        # Update job status
        jobs[job_id]["status"] = JobStatus.processing
        jobs[job_id]["message"] = "Initializing video generation..."
        jobs[job_id]["updated_at"] = datetime.now().isoformat()

        # Validate model
        model_config = get_model_config(request.model)
        if not model_config:
            raise ValueError(f"Unknown model: {request.model}")

        # Get GCS URI
        output_gcs_uri = get_default_gcs_uri()

        # Validate and correct options
        corrected_options = model_manager.validate_and_correct_options(
            request.model,
            number_of_videos=request.number_of_videos,
            duration_seconds=request.duration_seconds,
            aspect_ratio=request.aspect_ratio,
            resolution=request.resolution,
        )

        # Apply corrections
        number_of_videos = corrected_options.get("number_of_videos", request.number_of_videos)
        duration_seconds = corrected_options.get("duration_seconds", request.duration_seconds)

        # Update progress
        jobs[job_id]["progress"] = 10
        jobs[job_id]["message"] = "Creating generation configuration..."
        jobs[job_id]["updated_at"] = datetime.now().isoformat()

        # Create configuration
        config = GenerateVideosConfig(
            aspect_ratio=request.aspect_ratio,
            output_gcs_uri=output_gcs_uri,
            number_of_videos=number_of_videos,
            duration_seconds=duration_seconds,
            enhance_prompt=request.enhance_prompt,
        )

        # Start video generation
        jobs[job_id]["progress"] = 20
        jobs[job_id]["message"] = "Starting video generation..."
        jobs[job_id]["updated_at"] = datetime.now().isoformat()

        client = get_client()
        operation = client.models.generate_videos(
            model=model_config.api_model_name,
            prompt=request.prompt,
            config=config,
        )

        # Poll for completion
        jobs[job_id]["progress"] = 30
        jobs[job_id]["message"] = "Generating video (this may take 2-3 minutes)..."
        jobs[job_id]["updated_at"] = datetime.now().isoformat()

        start_time = time.time()
        while not getattr(operation, "done", False):
            await asyncio.sleep(5)
            
            try:
                client = get_client()
                operation = client.operations.get(operation)
            except Exception as e:
                # Continue waiting on refresh errors
                pass

            # Update progress
            elapsed = time.time() - start_time
            estimated_progress = min(95, 30 + (elapsed / 120) * 65)
            jobs[job_id]["progress"] = int(estimated_progress)
            jobs[job_id]["message"] = f"Processing... ({int(elapsed)}s elapsed)"
            jobs[job_id]["updated_at"] = datetime.now().isoformat()

            # Timeout after 10 minutes
            if elapsed > 600:
                raise TimeoutError("Video generation timed out after 10 minutes")

        # Check result
        if getattr(operation, "response", None):
            result = getattr(operation, "result", None)
            if result and hasattr(result, "generated_videos"):
                video_uris = [video.video.uri for video in result.generated_videos]
                
                # Update job with videos
                jobs[job_id]["progress"] = 95
                jobs[job_id]["message"] = "Downloading videos..."
                jobs[job_id]["updated_at"] = datetime.now().isoformat()

                # Download videos
                download_folder = "downloaded_media"
                downloaded_videos = download.download_media(
                    video_uris, 
                    download_folder, 
                    cleanup_gcs=True, 
                    organize_by_type=True
                )

                # Get relative paths for web access
                video_paths = []
                for video_path in downloaded_videos:
                    rel_path = os.path.relpath(video_path, download_folder)
                    video_paths.append(f"/media/{rel_path}")

                # Complete the job
                jobs[job_id]["status"] = JobStatus.completed
                jobs[job_id]["progress"] = 100
                jobs[job_id]["message"] = f"Successfully generated {len(video_paths)} video(s)"
                jobs[job_id]["videos"] = video_paths
                jobs[job_id]["updated_at"] = datetime.now().isoformat()
            else:
                raise ValueError("No videos were generated")
        else:
            error_msg = getattr(operation, "error", "Unknown error occurred")
            raise ValueError(str(error_msg))

    except Exception as e:
        jobs[job_id]["status"] = JobStatus.failed
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["message"] = f"Error: {str(e)}"
        jobs[job_id]["updated_at"] = datetime.now().isoformat()


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main web UI"""
    html_file = Path(__file__).parent / "static" / "index.html"
    if html_file.exists():
        return FileResponse(html_file)
    return HTMLResponse(content=get_embedded_html(), status_code=200)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/models", response_model=List[ModelInfo])
async def list_models():
    """List available AI models"""
    models = []
    for model_id, model in model_manager.video_models.items():
        config = get_model_config(model_id)
        if config:
            models.append(ModelInfo(
                id=model_id,
                name=config.display_name,
                description=config.description,
                max_videos=config.capabilities.max_videos,
                max_duration=config.capabilities.duration.max,
                resolutions=config.capabilities.resolutions,
                capabilities={
                    "supports_extend_video": config.capabilities.supports_extend_video,
                    "supports_image_to_video": config.capabilities.supports_image_to_video,
                    "supports_prompt_enhancement": config.capabilities.supports_prompt_enhancement,
                }
            ))
    return models


@app.post("/api/generate", response_model=JobResponse)
async def generate_video(request: GenerateVideoRequest, background_tasks: BackgroundTasks):
    """Generate a video from a text prompt"""
    # Create a new job
    job_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.queued,
        "progress": 0,
        "message": "Job queued",
        "videos": [],
        "error": None,
        "created_at": now,
        "updated_at": now,
        "request": request.model_dump()
    }

    # Start background task
    background_tasks.add_task(generate_video_task, job_id, request)

    return JobResponse(**jobs[job_id])


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """Get the status of a video generation job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobResponse(**jobs[job_id])


@app.get("/api/jobs", response_model=List[JobResponse])
async def list_jobs():
    """List all jobs"""
    return [JobResponse(**job) for job in jobs.values()]


@app.get("/media/{filepath:path}")
async def serve_media(filepath: str):
    """Serve generated media files"""
    media_path = Path("downloaded_media") / filepath
    
    if not media_path.exists() or not media_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")
    
    return FileResponse(media_path)


def get_embedded_html() -> str:
    """Get embedded HTML for the web UI (used when static files don't exist)"""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Media Studio - Web UI</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px;
                text-align: center;
            }
            .header h1 {
                font-size: 2.5rem;
                margin-bottom: 10px;
                font-weight: 700;
            }
            .header p {
                font-size: 1.1rem;
                opacity: 0.9;
            }
            .content {
                padding: 40px;
            }
            .form-group {
                margin-bottom: 25px;
            }
            label {
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #333;
                font-size: 0.95rem;
            }
            input, textarea, select {
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 1rem;
                transition: border-color 0.3s;
            }
            input:focus, textarea:focus, select:focus {
                outline: none;
                border-color: #667eea;
            }
            textarea {
                resize: vertical;
                min-height: 100px;
            }
            .row {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
            }
            .btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 15px 30px;
                border: none;
                border-radius: 8px;
                font-size: 1.1rem;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
                width: 100%;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
            }
            .btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
            }
            .status {
                margin-top: 30px;
                padding: 20px;
                background: #f5f5f5;
                border-radius: 12px;
                display: none;
            }
            .status.active {
                display: block;
            }
            .progress-bar {
                width: 100%;
                height: 8px;
                background: #e0e0e0;
                border-radius: 10px;
                overflow: hidden;
                margin: 15px 0;
            }
            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                transition: width 0.3s;
                width: 0%;
            }
            .videos-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            .video-card {
                background: white;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }
            .video-card video {
                width: 100%;
                display: block;
            }
            .video-card .actions {
                padding: 15px;
            }
            .video-card .actions a {
                color: #667eea;
                text-decoration: none;
                font-weight: 600;
            }
            .error {
                background: #fee;
                color: #c00;
                padding: 15px;
                border-radius: 8px;
                margin-top: 15px;
            }
            .success {
                background: #efe;
                color: #060;
                padding: 15px;
                border-radius: 8px;
                margin-top: 15px;
            }
            .info {
                background: #e3f2fd;
                color: #1976d2;
                padding: 15px;
                border-radius: 8px;
                margin-top: 15px;
            }
            .emoji {
                font-size: 1.2em;
                margin-right: 8px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎨 AI Media Studio</h1>
                <p>Generate professional videos with Google's AI models</p>
            </div>
            <div class="content">
                <form id="generateForm">
                    <div class="form-group">
                        <label for="prompt"><span class="emoji">✍️</span>Video Prompt</label>
                        <textarea 
                            id="prompt" 
                            name="prompt" 
                            placeholder="Describe your video... e.g., 'a majestic eagle soaring over mountains at sunset'"
                            required
                        ></textarea>
                    </div>

                    <div class="row">
                        <div class="form-group">
                            <label for="model"><span class="emoji">🤖</span>AI Model</label>
                            <select id="model" name="model" required>
                                <option value="">Loading models...</option>
                            </select>
                        </div>

                        <div class="form-group">
                            <label for="resolution"><span class="emoji">📐</span>Resolution</label>
                            <select id="resolution" name="resolution">
                                <option value="1080">1080p - Full HD</option>
                                <option value="720">720p - HD</option>
                            </select>
                        </div>
                    </div>

                    <div class="row">
                        <div class="form-group">
                            <label for="number_of_videos"><span class="emoji">🎬</span>Number of Videos</label>
                            <input 
                                type="number" 
                                id="number_of_videos" 
                                name="number_of_videos" 
                                min="1" 
                                max="4" 
                                value="1"
                            >
                        </div>

                        <div class="form-group">
                            <label for="duration_seconds"><span class="emoji">⏱️</span>Duration (seconds)</label>
                            <input 
                                type="number" 
                                id="duration_seconds" 
                                name="duration_seconds" 
                                min="5" 
                                max="8" 
                                value="8"
                            >
                        </div>
                    </div>

                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="enhance_prompt" name="enhance_prompt" checked>
                            <span class="emoji">✨</span>Enable AI Prompt Enhancement
                        </label>
                    </div>

                    <button type="submit" class="btn" id="generateBtn">
                        🚀 Generate Video
                    </button>
                </form>

                <div id="status" class="status">
                    <div id="statusMessage"></div>
                    <div class="progress-bar">
                        <div id="progressFill" class="progress-fill"></div>
                    </div>
                    <div id="progressText"></div>
                </div>

                <div id="videosContainer"></div>
            </div>
        </div>

        <script>
            const API_BASE = '';
            let currentJobId = null;
            let pollInterval = null;

            // Load available models
            async function loadModels() {
                try {
                    const response = await fetch(`${API_BASE}/api/models`);
                    const models = await response.json();
                    
                    const modelSelect = document.getElementById('model');
                    modelSelect.innerHTML = models.map(model => 
                        `<option value="${model.id}">${model.name} - ${model.description}</option>`
                    ).join('');
                } catch (error) {
                    console.error('Error loading models:', error);
                }
            }

            // Handle form submission
            document.getElementById('generateForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const formData = new FormData(e.target);
                const data = {
                    prompt: formData.get('prompt'),
                    model: formData.get('model'),
                    resolution: formData.get('resolution'),
                    number_of_videos: parseInt(formData.get('number_of_videos')),
                    duration_seconds: parseInt(formData.get('duration_seconds')),
                    enhance_prompt: formData.get('enhance_prompt') === 'on',
                    aspect_ratio: '16:9'
                };

                try {
                    document.getElementById('generateBtn').disabled = true;
                    document.getElementById('status').classList.add('active');
                    
                    const response = await fetch(`${API_BASE}/api/generate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data)
                    });

                    if (!response.ok) throw new Error('Generation failed');
                    
                    const result = await response.json();
                    currentJobId = result.job_id;
                    
                    // Start polling for status
                    pollInterval = setInterval(checkJobStatus, 2000);
                    updateStatus(result);
                } catch (error) {
                    showError('Error starting generation: ' + error.message);
                    document.getElementById('generateBtn').disabled = false;
                }
            });

            // Check job status
            async function checkJobStatus() {
                if (!currentJobId) return;

                try {
                    const response = await fetch(`${API_BASE}/api/jobs/${currentJobId}`);
                    const job = await response.json();
                    
                    updateStatus(job);

                    if (job.status === 'completed') {
                        clearInterval(pollInterval);
                        displayVideos(job.videos);
                        document.getElementById('generateBtn').disabled = false;
                        showSuccess(`Successfully generated ${job.videos.length} video(s)!`);
                    } else if (job.status === 'failed') {
                        clearInterval(pollInterval);
                        showError('Generation failed: ' + (job.error || 'Unknown error'));
                        document.getElementById('generateBtn').disabled = false;
                    }
                } catch (error) {
                    console.error('Error checking status:', error);
                }
            }

            // Update status display
            function updateStatus(job) {
                document.getElementById('statusMessage').innerHTML = 
                    `<div class="info"><strong>Status:</strong> ${job.message}</div>`;
                document.getElementById('progressFill').style.width = job.progress + '%';
                document.getElementById('progressText').textContent = 
                    `Progress: ${job.progress}%`;
            }

            // Display generated videos
            function displayVideos(videos) {
                const container = document.getElementById('videosContainer');
                container.innerHTML = `
                    <h2 style="margin-top: 30px; margin-bottom: 20px;">Generated Videos</h2>
                    <div class="videos-grid">
                        ${videos.map((video, i) => `
                            <div class="video-card">
                                <video controls>
                                    <source src="${video}" type="video/mp4">
                                </video>
                                <div class="actions">
                                    <a href="${video}" download>⬇️ Download Video ${i + 1}</a>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            // Show error message
            function showError(message) {
                const status = document.getElementById('status');
                status.classList.add('active');
                status.innerHTML = `<div class="error">${message}</div>`;
            }

            // Show success message
            function showSuccess(message) {
                const statusMessage = document.getElementById('statusMessage');
                statusMessage.innerHTML = `<div class="success">${message}</div>`;
            }

            // Initialize
            loadModels();
        </script>
    </body>
    </html>
    """


def start_server():
    """Start the web server"""
    import uvicorn
    print("🎨 AI Media Studio Web UI")
    print("=" * 50)
    print("Starting web server on http://localhost:8080")
    print("=" * 50)
    print("\n✨ Features:")
    print("  • Generate videos with Google's AI models")
    print("  • Real-time progress tracking")
    print("  • Auto-download and preview videos")
    print("  • Support for multiple models and resolutions")
    print("\n📝 Make sure to configure your .env file with:")
    print("  • GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT")
    print("  • GOOGLE_CLOUD_STORAGE_BUCKET")
    print("\nPress CTRL+C to stop the server\n")
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    start_server()
