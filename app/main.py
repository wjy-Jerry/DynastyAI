from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.models import Project, StoryRequest
from app.storyboard import GenerationError, generate

app = FastAPI(title="DynastyAI", version="0.1.0")
STATIC = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def get_settings() -> Settings:
    return Settings()


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health(settings: Settings = Depends(get_settings)):
    return {
        "status": "ok",
        "mode": "demo" if settings.demo_mode else "llm",
        "configured": settings.demo_mode or bool(settings.llm_api_key.strip()),
    }


@app.post("/api/storyboards", response_model=Project)
async def create_storyboard(request: StoryRequest, settings: Settings = Depends(get_settings)):
    try:
        return await generate(request, settings)
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/projects/validate", response_model=Project)
def validate_project(project: Project):
    return project
