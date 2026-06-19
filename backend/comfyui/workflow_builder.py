from __future__ import annotations

import random
from typing import Any


class WorkflowBuilder:
    """
    Constructs ComfyUI workflow graphs (node dicts) programmatically.
    Each method returns a dict suitable for the /prompt endpoint.
    """

    def attach_mock_metadata(
        self,
        graph: dict[str, Any],
        *,
        model_id: str,
        visual_theme: str,
        output_kind: str,
        pollinations_model: str | None = None,
        source_asset_url: str | None = None,
        source_asset_type: str | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
        duration_sec: float | None = None,
    ) -> dict[str, Any]:
        graph["mock_meta"] = {
            "class_type": "MockModelInfo",
            "inputs": {
                "model_id": model_id,
                "visual_theme": visual_theme,
                "output_kind": output_kind,
                "pollinations_model": pollinations_model or "",
                "source_asset_url": source_asset_url or "",
                "source_asset_type": source_asset_type or "",
                "width": int(width or 0),
                "height": int(height or 0),
                "fps": int(fps or 0),
                "duration_sec": float(duration_sec or 0),
            },
        }
        return graph

    def build_mock_audio(
        self,
        prompt: str,
        model_id: str = "eleven-v3",
        visual_theme: str = "eleven",
    ) -> dict[str, Any]:
        graph: dict[str, Any] = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        }
        return self.attach_mock_metadata(graph, model_id=model_id, visual_theme=visual_theme, output_kind="audio")

    # ── SDXL Text-to-Image ────────────────────────────────────────────────────
    def build_sdxl_txt2img(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 576,
        steps: int = 30,
        cfg: float = 7.0,
        seed: int | None = None,
        sampler: str = "dpmpp_2m",
        scheduler: str = "karras",
        ip_adapter_enabled: bool = False,
        ip_adapter_scale: float = 0.6,
    ) -> dict[str, Any]:
        seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        graph: dict[str, Any] = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": sampler,
                    "scheduler": scheduler,
                    "denoise": 1.0,
                },
            },
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "txt2img"}},
        }

        if ip_adapter_enabled:
            graph = self._inject_ip_adapter(graph, scale=ip_adapter_scale)

        return graph

    # ── SDXL Image-to-Image ───────────────────────────────────────────────────
    def build_sdxl_img2img(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 576,
        steps: int = 30,
        cfg: float = 7.0,
        denoise: float = 0.75,
        seed: int | None = None,
    ) -> dict[str, Any]:
        seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["1", 1]}},
            "4": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
            "4b": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4b", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": denoise,
                },
            },
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "img2img"}},
        }

    # ── AnimateDiff Text-to-Video ─────────────────────────────────────────────
    def build_animatediff_txt2vid(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 512,
        height: int = 512,
        num_frames: int = 16,
        fps: int = 8,
        steps: int = 20,
        cfg: float = 7.0,
        seed: int | None = None,
        motion_module: str = "mm_sd_v15_v2.ckpt",
        motion_scale: float = 1.0,
        ip_adapter_enabled: bool = False,
        ip_adapter_scale: float = 0.6,
    ) -> dict[str, Any]:
        seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        graph: dict[str, Any] = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "v1-5-pruned-emaonly.ckpt"}},
            "2": {"class_type": "ADE_AnimateDiffLoaderWithContext", "inputs": {
                "model": ["1", 0],
                "motion_module": motion_module,
                "beta_schedule": "sqrt_linear (AnimateDiff)",
                "motion_scale": motion_scale,
            }},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["1", 1]}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": num_frames}},
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["2", 0],
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "latent_image": ["5", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0,
                },
            },
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
            "8": {"class_type": "ADE_AnimateDiffCombine", "inputs": {
                "images": ["7", 0],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": "animatediff",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
            }},
        }

        if ip_adapter_enabled:
            graph = self._inject_ip_adapter_sd15(graph, scale=ip_adapter_scale)

        return graph

    # ── AnimateDiff Image-to-Video ────────────────────────────────────────────
    def build_animatediff_img2vid(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 512,
        height: int = 512,
        num_frames: int = 16,
        fps: int = 8,
        steps: int = 20,
        cfg: float = 7.0,
        denoise: float = 0.85,
        seed: int | None = None,
    ) -> dict[str, Any]:
        seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "v1-5-pruned-emaonly.ckpt"}},
            "2": {"class_type": "ADE_AnimateDiffLoaderWithContext", "inputs": {
                "model": ["1", 0], "motion_module": "mm_sd_v15_v2.ckpt",
                "beta_schedule": "sqrt_linear (AnimateDiff)", "motion_scale": 1.0,
            }},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["1", 1]}},
            "img_load": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
            "img_enc": {"class_type": "VAEEncode", "inputs": {"pixels": ["img_load", 0], "vae": ["1", 2]}},
            "tile": {"class_type": "RepeatLatentBatch", "inputs": {"samples": ["img_enc", 0], "amount": num_frames}},
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0],
                    "latent_image": ["tile", 0], "seed": seed, "steps": steps,
                    "cfg": cfg, "sampler_name": "dpmpp_2m", "scheduler": "karras",
                    "denoise": denoise,
                },
            },
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
            "8": {"class_type": "ADE_AnimateDiffCombine", "inputs": {
                "images": ["7", 0], "frame_rate": fps, "loop_count": 0,
                "filename_prefix": "img2vid", "format": "video/h264-mp4",
                "pingpong": False, "save_output": True,
            }},
        }

    # ── Video Upscale ─────────────────────────────────────────────────────────
    def build_video_upscale(
        self,
        input_url: str,
        scale_factor: int = 2,
    ) -> dict[str, Any]:
        return {
            "load": {"class_type": "LoadVideoPath", "inputs": {"video": input_url, "force_rate": 0}},
            "upscale_model": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "RealESRGAN_x4plus.pth"}},
            "upscale": {"class_type": "ImageUpscaleWithModel", "inputs": {
                "upscale_model": ["upscale_model", 0], "image": ["load", 0],
            }},
            "save": {"class_type": "SaveAnimatedWEBP", "inputs": {
                "images": ["upscale", 0], "filename_prefix": "upscaled",
                "fps": 24, "lossless": False, "quality": 90, "method": "default",
            }},
        }

    # ── Video Enhancement ────────────────────────────────────────────────────
    def build_video_enhance(
        self,
        prompt: str,
        negative_prompt: str = "",
        strength: float = 0.8,
    ) -> dict[str, Any]:
        """
        Enhance an uploaded video with a prompt-driven style/effect.
        For mock: returns a simple workflow. In production, uses real enhancement models.
        """
        return {
            "prompt_text": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "save": {"class_type": "SaveAnimatedWEBP", "inputs": {
                "images": [["prompt_text", 0]], "filename_prefix": "enhanced",
                "fps": 12, "lossless": False, "quality": 85, "method": "default",
            }},
        }

    # ── IP-Adapter Injection Helpers ──────────────────────────────────────────
    def _inject_ip_adapter(self, graph: dict, scale: float = 0.6) -> dict:
        """Inject IP-Adapter nodes into an SDXL graph (modifies in-place)."""
        graph["ipa_loader"] = {"class_type": "IPAdapterModelLoader", "inputs": {
            "ipadapter_file": "ip-adapter-plus_sdxl_vit-h.safetensors",
        }}
        graph["clip_vision"] = {"class_type": "CLIPVisionLoader", "inputs": {
            "clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
        }}
        graph["ref_image"] = {"class_type": "LoadImage", "inputs": {"image": "reference.png"}}
        graph["ipa_apply"] = {"class_type": "IPAdapterApply", "inputs": {
            "ipadapter": ["ipa_loader", 0],
            "clip_vision": ["clip_vision", 0],
            "image": ["ref_image", 0],
            "model": ["1", 0],
            "weight": scale,
            "noise": 0.0,
            "weight_type": "original",
            "start_at": 0.0,
            "end_at": 1.0,
            "unfold_batch": False,
        }}
        # Rewire KSampler to use IP-Adapter patched model
        graph["5"]["inputs"]["model"] = ["ipa_apply", 0]
        return graph

    def _inject_ip_adapter_sd15(self, graph: dict, scale: float = 0.6) -> dict:
        """Inject IP-Adapter nodes into a SD 1.5 / AnimateDiff graph."""
        graph["ipa_loader"] = {"class_type": "IPAdapterModelLoader", "inputs": {
            "ipadapter_file": "ip-adapter-plus_sd15.safetensors",
        }}
        graph["clip_vision"] = {"class_type": "CLIPVisionLoader", "inputs": {
            "clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
        }}
        graph["ref_image"] = {"class_type": "LoadImage", "inputs": {"image": "reference.png"}}
        graph["ipa_apply"] = {"class_type": "IPAdapterApply", "inputs": {
            "ipadapter": ["ipa_loader", 0],
            "clip_vision": ["clip_vision", 0],
            "image": ["ref_image", 0],
            "model": ["1", 0],
            "weight": scale,
            "noise": 0.0,
            "weight_type": "original",
            "start_at": 0.0,
            "end_at": 1.0,
            "unfold_batch": False,
        }}
        graph["2"]["inputs"]["model"] = ["ipa_apply", 0]
        return graph
