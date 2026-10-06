import re

from app.phase2_models import Character, ProjectV2, SceneV2, VisualStyle


def slug_for_name(name: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24]
    return f"character-{index}-{slug}" if slug else f"character-{index}"


def character_block(character: Character) -> str:
    return "\n".join(
        [
            f"CHARACTER ID: {character.id}",
            f"Name: {character.name}",
            f"Role: {character.role}",
            f"Approximate age: {character.approximate_age}",
            f"Appearance: {character.appearance}",
            f"Facial features: {character.facial_features}",
            f"Hairstyle: {character.hairstyle}",
            f"Costume: {character.costume}",
            f"Accessories: {character.accessories}",
            f"Personality / visual impression: {character.personality_visual_impression}",
        ]
    )


def style_block(style: VisualStyle) -> str:
    return "\n".join(
        [
            "VISUAL STYLE BIBLE",
            f"Historical era / dynasty: {style.historical_era}",
            f"Visual style: {style.visual_style}",
            f"Lighting: {style.lighting}",
            f"Cinematography: {style.cinematography}",
            f"Color mood: {style.color_mood}",
            f"Aspect ratio: {style.aspect_ratio} vertical short-form frame",
        ]
    )


def compose_prompt(scene: SceneV2, characters: list[Character], style: VisualStyle) -> str:
    by_id = {character.id: character for character in characters}
    blocks = [character_block(by_id[identifier]) for identifier in scene.character_ids]
    return "\n\n".join(
        [
            "Create a single cinematic keyframe for a fictional Chinese historical drama. "
            "The setting is historically inspired; do not imply verified historical accuracy. "
            "Keep recurring characters visually aligned with these exact descriptions. "
            "No subtitles, captions, watermarks, or contact sheets.",
            style_block(style),
            "SCENE DIRECTION\n"
            f"Scene number: {scene.scene_number}\n"
            f"Visual action and setting: {scene.visual_prompt}\n"
            f"Camera: {scene.camera_description}",
            "CHARACTER BIBLE ENTRIES\n" + "\n\n".join(blocks),
        ]
    )


def prompt_is_current(project: ProjectV2, scene: SceneV2) -> bool:
    by_id = {character.id: character for character in project.character_bible}
    required = [
        style_block(project.visual_style),
        f"Visual action and setting: {scene.visual_prompt}",
        f"Camera: {scene.camera_description}",
    ] + [character_block(by_id[identifier]) for identifier in scene.character_ids]
    return all(block in scene.final_image_prompt for block in required)


def refresh_prompts(project: ProjectV2) -> ProjectV2:
    for scene in project.scenes:
        scene.final_image_prompt = compose_prompt(
            scene, project.character_bible, project.visual_style
        )
    return project
