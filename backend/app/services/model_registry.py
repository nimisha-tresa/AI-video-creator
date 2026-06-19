from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GenerationKind = Literal["text_to_video", "image_to_video", "text_to_image", "text_to_audio"]


@dataclass(frozen=True)
class ModelPreset:
    fps: int = 12
    steps: int = 20
    cfg: float = 7.0
    motion_scale: float = 1.0
    visual_theme: str = "default"
    duration_sec: int = 6


@dataclass(frozen=True)
class StudioModel:
    id: str
    name: str
    provider: str
    category: Literal["video", "image", "audio", "llm"]
    generation_type: GenerationKind
    description: str
    badge: str | None
    preset: ModelPreset
    pollinations_model: str | None = None
    compatible: bool = True


STUDIO_MODELS: list[StudioModel] = [
    StudioModel(
        id="veo-3.1",
        name="Veo 3.1",
        provider="Google",
        category="video",
        generation_type="text_to_video",
        description="Cinematic text-to-video with smooth camera motion.",
        badge="Video",
        preset=ModelPreset(fps=24, steps=28, visual_theme="veo", duration_sec=8),
        pollinations_model="veo",
    ),
    StudioModel(
        id="sora-2-pro",
        name="Sora 2 Pro",
        provider="OpenAI",
        category="video",
        generation_type="text_to_video",
        description="High-fidelity scene generation with rich detail.",
        badge="Pro",
        preset=ModelPreset(fps=24, steps=30, visual_theme="sora", duration_sec=10),
        pollinations_model="ltx-2",
    ),
    StudioModel(
        id="kling-3.0",
        name="Kling 3.0",
        provider="Kuaishou",
        category="video",
        generation_type="image_to_video",
        description="Animate still images into dynamic clips.",
        badge="I2V",
        preset=ModelPreset(fps=16, steps=24, motion_scale=1.2, visual_theme="kling", duration_sec=6),
        pollinations_model="wan",
    ),
    StudioModel(
        id="seedance-2.0",
        name="Seedance 2.0",
        provider="ByteDance",
        category="video",
        generation_type="text_to_video",
        description="Dance and motion-focused video generation.",
        badge="Motion",
        preset=ModelPreset(fps=16, steps=22, motion_scale=1.4, visual_theme="seedance", duration_sec=6),
        pollinations_model="seedance",
    ),
    StudioModel(
        id="wan-2.6-pro",
        name="WAN2.6 Pro",
        provider="Alibaba",
        category="video",
        generation_type="text_to_video",
        description="Fast professional video synthesis.",
        badge="Pro",
        preset=ModelPreset(fps=12, steps=20, visual_theme="wan", duration_sec=6),
        pollinations_model="wan2.6",
    ),
    StudioModel(
        id="gen-4.5",
        name="Gen-4.5",
        provider="Runway",
        category="video",
        generation_type="text_to_video",
        description="Creative direction with strong temporal consistency.",
        badge="Gen",
        preset=ModelPreset(fps=12, steps=26, visual_theme="gen", duration_sec=8),
        pollinations_model="seedance-pro",
    ),
    StudioModel(
        id="flux-2-max",
        name="FLUX.2 [max]",
        provider="Black Forest Labs",
        category="image",
        generation_type="text_to_image",
        description="Maximum quality photorealistic still frames.",
        badge="Max",
        preset=ModelPreset(steps=32, visual_theme="flux"),
    ),
    StudioModel(
        id="seedream-5.0",
        name="Seedream 5.0",
        provider="ByteDance",
        category="image",
        generation_type="text_to_image",
        description="Dreamlike stylized image generation.",
        badge="Image",
        preset=ModelPreset(steps=28, visual_theme="seedream"),
    ),
    StudioModel(
        id="nano-banana-2",
        name="Nano Banana 2",
        provider="Google",
        category="image",
        generation_type="text_to_image",
        description="Lightweight fast image generation.",
        badge="Fast",
        preset=ModelPreset(steps=16, visual_theme="banana"),
    ),
    StudioModel(
        id="nano-banana-pro",
        name="Nano Banana Pro",
        provider="Google",
        category="image",
        generation_type="text_to_image",
        description="Pro-tier image quality with fast turnaround.",
        badge="Pro",
        preset=ModelPreset(steps=24, visual_theme="banana-pro"),
    ),
    StudioModel(
        id="eleven-v3",
        name="Eleven v3",
        provider="ElevenLabs",
        category="audio",
        generation_type="text_to_audio",
        description="Natural voice and soundscape generation from text.",
        badge="Audio",
        preset=ModelPreset(visual_theme="eleven"),
    ),
    StudioModel(
        id="claude-opus-4.6",
        name="Claude Opus 4.6",
        provider="Anthropic",
        category="llm",
        generation_type="text_to_image",
        description="Prompt expansion and storyboard frame generation.",
        badge="LLM",
        preset=ModelPreset(steps=20, visual_theme="claude"),
    ),
]


def get_model(model_id: str) -> StudioModel | None:
    return next((m for m in STUDIO_MODELS if m.id == model_id), None)


def list_models() -> list[StudioModel]:
    return list(STUDIO_MODELS)
