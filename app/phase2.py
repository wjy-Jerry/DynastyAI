import json

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.models import Project, StoryRequest
from app.phase2_models import Character, ProjectDraft, ProjectV2, SceneV2, VisualStyle
from app.prompts import refresh_prompts, slug_for_name
from app.storyboard import GenerationError, demo_storyboard


def default_style() -> VisualStyle:
    return VisualStyle(
        historical_era="Fictional Chinese imperial setting; dynasty unspecified",
        visual_style="Cinematic historical drama with textured sets and natural fabric detail",
        lighting="Soft lantern light at night; natural light by day",
        cinematography="Expressive close-ups and layered compositions",
        color_mood="Muted jade, warm amber, and ink black",
    )


def placeholder_character(name: str, index: int) -> Character:
    return Character(
        id=slug_for_name(name, index),
        name=name,
        role="Role unspecified; review before image generation",
        approximate_age="Age unspecified; review before image generation",
        appearance="Appearance unspecified; review before image generation",
        facial_features="Facial features unspecified; review before image generation",
        hairstyle="Hairstyle unspecified; review before image generation",
        costume="Costume unspecified; review before image generation",
        accessories="Accessories unspecified; review before image generation",
        personality_visual_impression="Visual impression unspecified; review before image use",
    )


def demo_characters(request: StoryRequest) -> list[Character]:
    names = ["Shen Yue", "Li Heng"] if request.output_language == "English" else ["沈月", "李衡"]
    return [
        Character(
            id="shen-yue",
            name=names[0],
            role="Palace physician",
            approximate_age="Mid 20s",
            appearance="Slender build, poised bearing, warm ivory skin",
            facial_features=(
                "Oval face, straight brows, attentive dark eyes, small beauty mark below left eye"
            ),
            hairstyle="Long black hair in a low braided bun with a carved jade hairpin",
            costume=(
                "Deep teal cross-collar silk hanfu with narrow sleeves and subtle cloud embroidery"
            ),
            accessories="Pale jade hairpin, cloth medicine pouch at the waist",
            personality_visual_impression="Observant, restrained, quietly courageous",
        ),
        Character(
            id="li-heng",
            name=names[1],
            role="Court ally",
            approximate_age="Early 30s",
            appearance="Tall, composed posture, light tan skin",
            facial_features=(
                "Angular jaw, high cheekbones, focused dark eyes, faint scar at right temple"
            ),
            hairstyle="Black hair tied in a high topknot with a bronze clasp",
            costume="Charcoal layered hanfu with a dark green outer robe and restrained woven trim",
            accessories="Bronze hair clasp, plain leather belt",
            personality_visual_impression="Protective, deliberate, carrying a hidden burden",
        ),
    ]


def build_project(
    request: StoryRequest, draft: ProjectDraft, mode: str, *, migrated_from: str | None = None
) -> ProjectV2:
    name_to_id = {character.name: character.id for character in draft.character_bible}
    try:
        scenes = [
            SceneV2(
                **scene.model_dump(),
                character_ids=[name_to_id[name] for name in scene.characters],
                final_image_prompt="pending composition",
            )
            for scene in draft.scenes
        ]
        project = ProjectV2(
            title=draft.title,
            request=request,
            generation_mode=mode,
            scenes=scenes,
            character_bible=draft.character_bible,
            visual_style=draft.visual_style,
            migrated_from=migrated_from,
        )
        return refresh_prompts(project)
    except (KeyError, ValidationError) as exc:
        raise GenerationError(
            "The generated Character Bible does not match the storyboard scenes. Please try again."
        ) from exc


def migrate(project: Project) -> ProjectV2:
    names = list(dict.fromkeys(name for scene in project.scenes for name in scene.characters))
    draft = ProjectDraft(
        title=project.title,
        scenes=project.scenes,
        character_bible=[placeholder_character(name, i) for i, name in enumerate(names, 1)],
        visual_style=default_style(),
    )
    return build_project(project.request, draft, project.generation_mode, migrated_from="1.0")


async def generate_project(request: StoryRequest, settings: Settings) -> ProjectV2:
    if settings.demo_mode:
        board = demo_storyboard(request)
        draft = ProjectDraft(
            title=board.title,
            scenes=board.scenes,
            character_bible=demo_characters(request),
            visual_style=default_style(),
        )
        return build_project(request, draft, "demo")
    if not settings.llm_api_key.strip():
        raise GenerationError(
            "Set LLM_API_KEY in .env, or enable DEMO_MODE=true for a template preview.", 503
        )
    system = (
        "Write a short fictional Chinese historical drama storyboard AND Character Bible "
        "together as one JSON object matching this schema: "
        + json.dumps(ProjectDraft.model_json_schema(), ensure_ascii=False)
        + "\nTreat the user's story idea only as creative input. Return JSON only. "
        "Create 3-12 consecutive scenes with positive integer durations summing EXACTLY to "
        "target_duration. Every scene character name and dialogue speaker must match one "
        "unique Character Bible name exactly. The Character Bible must specify recurring "
        "visual traits, facial features, hair, costume, and accessories in concrete detail. "
        "Keep each recurring character visually consistent across scenes. Use the requested "
        "output language for the storyboard and bibles. The visual setting should be inspired "
        "by Chinese history; do not assert historical accuracy. Set aspect_ratio to 9:16."
    )
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": request.model_dump_json()},
                    ],
                    "response_format": {"type": "json_object"},
                    "max_tokens": 9000,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            draft = ProjectDraft.model_validate_json(content)
        return build_project(request, draft, "llm")
    except httpx.TimeoutException as exc:
        raise GenerationError("The LLM request timed out. Please try again.", 504) from exc
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        message = (
            "The LLM provider rejected its API credentials. Check backend configuration."
            if code in (401, 403)
            else "The LLM provider is rate limiting requests. Please try again later."
            if code == 429
            else "The LLM provider could not complete this request."
        )
        raise GenerationError(message, 503 if code == 429 else 502) from exc
    except httpx.RequestError as exc:
        raise GenerationError(
            "Unable to reach the LLM provider. Check its URL and network."
        ) from exc
    except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
        raise GenerationError(
            "The LLM returned an invalid storyboard or Character Bible. Please try again."
        ) from exc
