from pathlib import Path
from uuid import UUID

from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.config import Settings
from app.images import ImageProviderError, asset_path, generate_scene_image
from app.models import Project, StoryRequest
from app.phase2 import generate_project, migrate
from app.phase2_models import ImageResult, ProjectV2
from app.prompts import prompt_is_current, refresh_prompts
from app.storyboard import GenerationError, generate

app = FastAPI(title="DynastyAI", version="0.2.0")
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


@app.get("/api/image-health")
def image_health(settings: Settings = Depends(get_settings)):
    return {
        "provider": settings.image_provider,
        "configured": settings.image_provider == "mock"
        or (
            settings.image_provider in ("openai", "alibaba")
            and bool(settings.image_api_key.strip())
        ),
    }


@app.post("/api/storyboards", response_model=Project | ProjectV2)
async def create_storyboard(
    request: StoryRequest,
    settings: Settings = Depends(get_settings),
    x_dynastyai_version: str = Header(default="1"),
):
    try:
        if x_dynastyai_version == "2":
            return await generate_project(request, settings)
        if x_dynastyai_version != "1":
            raise HTTPException(status_code=400, detail="Unsupported storyboard API version.")
        return await generate(request, settings)
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/projects", response_model=ProjectV2)
async def create_project(request: StoryRequest, settings: Settings = Depends(get_settings)):
    try:
        return await generate_project(request, settings)
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/projects/validate", response_model=Project | ProjectV2)
def validate_project(project: dict = Body(...)):
    version = project.get("schema_version")
    if version not in ("1.0", "2.0"):
        raise HTTPException(
            status_code=422,
            detail="Unsupported project schema version. Supported versions: 1.0 and 2.0.",
        )
    try:
        return (Project if version == "1.0" else ProjectV2).model_validate(project)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=exc.errors(include_input=False, include_context=False)
        ) from exc


@app.post("/api/projects/migrate", response_model=ProjectV2)
def migrate_project(project: Project):
    return migrate(project)


@app.post("/api/projects/prompts/refresh", response_model=ProjectV2)
def refresh_project_prompts(project: ProjectV2):
    return refresh_prompts(project)


@app.post("/api/images/scenes/{scene_number}", response_model=ImageResult)
async def create_scene_image(
    scene_number: int, project: ProjectV2, settings: Settings = Depends(get_settings)
):
    if scene_number < 1 or scene_number > len(project.scenes):
        raise HTTPException(status_code=404, detail="Scene not found in this project.")
    scene = project.scenes[scene_number - 1]
    if not prompt_is_current(project, scene):
        raise HTTPException(
            status_code=409,
            detail=(
                "Character, style, or scene direction changed. Refresh prompts before generating."
            ),
        )
    try:
        asset = await generate_scene_image(project, scene, settings)
        return ImageResult(image_asset=asset)
    except ImageProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/assets/{project_id}/{asset_id}")
def get_asset(project_id: UUID, asset_id: UUID, settings: Settings = Depends(get_settings)):
    for extension, media_type in (("png", "image/png"), ("svg", "image/svg+xml")):
        path = asset_path(settings, project_id, asset_id, extension)
        if path.is_file():
            return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})
    raise HTTPException(status_code=404, detail="Image asset is not present on this machine.")
