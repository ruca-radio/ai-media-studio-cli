# 🌐 AI Media Studio - Web UI

The AI Media Studio now includes a beautiful web interface for generating AI videos! Access all the powerful features of the CLI through an intuitive browser-based UI.

![Web UI Screenshot](https://github.com/user-attachments/assets/766c8ea3-b7cb-45c7-b3f7-a528fc67d117)

## 🚀 Quick Start

### Starting the Web Server

```bash
# Option 1: Using the CLI command (recommended)
ai-studio-web

# Option 2: Using Python module
python -m uvicorn ai_media_studio_cli.web_app:app --host 0.0.0.0 --port 8080
```

The web interface will be available at: **http://localhost:8080**

## ✨ Web UI Features

### 🎬 **Video Generation Interface**
- **Beautiful, Modern Design** - Clean and intuitive interface
- **Real-time Progress Tracking** - See generation progress with live updates
- **Video Preview** - Watch generated videos directly in the browser
- **Download Support** - One-click download of generated videos
- **Multiple Models** - Choose from Veo 2.0, Veo 3.0, and preview models

### 🎯 **Smart Configuration**
- **Prompt Input** - Large text area for detailed video descriptions
- **Model Selection** - Dropdown with all available AI models and their capabilities
- **Resolution Control** - Choose between 720p and 1080p quality
- **Video Count** - Generate 1-4 videos simultaneously
- **Duration Settings** - Set video length (5-8 seconds)
- **AI Enhancement** - Toggle prompt optimization on/off

### 📊 **Job Management**
- **Background Processing** - Generate videos without blocking the UI
- **Status Tracking** - Monitor job progress with percentage and messages
- **Job History** - View all generation jobs via API
- **Error Handling** - Clear error messages and retry options

## 🔌 API Endpoints

The web UI is powered by a RESTful API that you can also use programmatically:

### Health Check
```bash
GET /api/health
```

### List Available Models
```bash
GET /api/models
```

**Response:**
```json
[
  {
    "id": "veo3-001",
    "name": "Veo 3.0 Generate 001",
    "description": "Stable text-to-video generation",
    "max_videos": 4,
    "max_duration": 8,
    "resolutions": ["720p", "1080p"],
    "capabilities": {
      "supports_extend_video": false,
      "supports_image_to_video": false,
      "supports_prompt_enhancement": true
    }
  }
]
```

### Generate Video
```bash
POST /api/generate
Content-Type: application/json

{
  "prompt": "a majestic eagle soaring over mountains at sunset",
  "model": "veo3-001",
  "aspect_ratio": "16:9",
  "resolution": "1080",
  "number_of_videos": 1,
  "duration_seconds": 8,
  "enhance_prompt": true
}
```

**Response:**
```json
{
  "job_id": "uuid-here",
  "status": "queued",
  "progress": 0,
  "message": "Job queued",
  "videos": [],
  "error": null,
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:00:00"
}
```

### Check Job Status
```bash
GET /api/jobs/{job_id}
```

**Response:**
```json
{
  "job_id": "uuid-here",
  "status": "completed",
  "progress": 100,
  "message": "Successfully generated 1 video(s)",
  "videos": ["/media/videos/video_uuid.mp4"],
  "error": null,
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:02:30"
}
```

### List All Jobs
```bash
GET /api/jobs
```

### Download Media
```bash
GET /media/{filepath}
```

## 🏗️ Architecture

### Backend: FastAPI
- **Modern Python Framework** - Async support out of the box
- **Automatic API Documentation** - OpenAPI/Swagger UI at `/docs`
- **Type Safety** - Pydantic models for request/response validation
- **Background Tasks** - Non-blocking video generation

### Frontend: Pure HTML/CSS/JavaScript
- **No Build Step** - Simple deployment
- **Embedded UI** - HTML served directly by FastAPI
- **Responsive Design** - Works on desktop and mobile
- **Real-time Updates** - Polling-based progress tracking

### Integration
- **Minimal Changes** - Wraps existing CLI logic
- **Shared Code** - Uses same model manager and download utilities
- **Configuration** - Reads from same `.env` file as CLI

## ⚙️ Configuration

The web UI uses the same `.env` configuration as the CLI:

```env
# 🔑 Google AI API Configuration
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=True
GOOGLE_API_KEY=your-google-api-key

# 🪣 Google Cloud Storage Configuration
GOOGLE_CLOUD_STORAGE_BUCKET=your-bucket-name
GOOGLE_CLOUD_STORAGE_PATH=videos
```

## 🔧 Advanced Usage

### Custom Port
```bash
python -m uvicorn ai_media_studio_cli.web_app:app --host 0.0.0.0 --port 3000
```

### Production Deployment
```bash
# With multiple workers
uvicorn ai_media_studio_cli.web_app:app \
  --host 0.0.0.0 \
  --port 8080 \
  --workers 4 \
  --access-log

# With Gunicorn
gunicorn ai_media_studio_cli.web_app:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  -b 0.0.0.0:8080
```

### Docker Deployment
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install -e .

EXPOSE 8080

CMD ["ai-studio-web"]
```

## 🎨 Use Cases

### 🎬 **Content Creators**
- Generate video B-roll for projects
- Create social media content quickly
- Experiment with different prompts visually

### 👨‍💻 **Developers**
- Integrate video generation into web apps
- Build custom workflows with the API
- Prototype AI-powered features

### 🏢 **Teams**
- Share video generation capabilities
- Centralized video production
- No CLI knowledge required

## 🛣️ Future Enhancements

- [ ] WebSocket support for real-time progress (instead of polling)
- [ ] Video extension support in the web UI
- [ ] Image-to-video generation interface
- [ ] Batch generation UI
- [ ] User authentication and multi-tenancy
- [ ] Video gallery and management
- [ ] Advanced prompt builder
- [ ] Cost tracking and analytics
- [ ] Custom model fine-tuning interface

## 🤝 CLI + Web UI

Both interfaces work together seamlessly:

```bash
# Generate via CLI
ai-studio generate -p "your prompt here"

# Start web UI to preview downloaded videos
ai-studio-web

# Or use both - CLI for automation, Web UI for exploration
```

## 📝 Notes

- **State Management**: Jobs are stored in-memory (resets on server restart)
- **Production**: Use Redis/database for persistent job storage
- **Media Files**: Automatically organized in `downloaded_media/` folder
- **CORS**: Currently allows all origins (configure for production)
- **Cleanup**: Generated videos are automatically downloaded and GCS files cleaned up

## 🆘 Troubleshooting

### Port Already in Use
```bash
# Check what's using the port
lsof -i :8080

# Use a different port
python -m uvicorn ai_media_studio_cli.web_app:app --port 3000
```

### API Key Issues
```bash
# Verify .env file exists and has required keys
cat .env

# Check environment variables are loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('GOOGLE_API_KEY'))"
```

### Video Generation Fails
- Check your Google Cloud credentials
- Verify GCS bucket exists and has correct permissions
- Ensure sufficient quota for video generation API
- Check server logs for detailed error messages

---

**🎉 Enjoy generating amazing videos with the AI Media Studio Web UI!**

For more information about the CLI, see the main [README.md](../README.md).
