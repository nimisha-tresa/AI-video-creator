"""Pollinations true-video + motion-synthesis engine."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

CACHE_DIR = Path("/tmp/mock_outputs")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "").strip()

# Studio model id → Pollinations video model (https://gen.pollinations.ai/video/...)
STUDIO_VIDEO_MODELS: dict[str, str] = {
    "veo-3.1": "veo",
    "sora-2-pro": "ltx-2",
    "kling-3.0": "wan",
    "seedance-2.0": "seedance",
    "wan-2.6-pro": "wan2.6",
    "gen-4.5": "seedance-pro",
}

POLLINATIONS_FALLBACK_MODELS = ["veo", "seedance", "wan", "wan-fast", "ltx-2", "seedance-pro"]

SCENE_KEYWORDS: dict[str, list[str]] = {
    "ocean": ["ocean", "sea", "beach", "wave", "coast", "underwater", "surf"],
    "mountain": ["mountain", "peak", "alpine", "summit", "hills", "valley"],
    "city": ["city", "urban", "street", "neon", "skyline", "downtown", "metropolis"],
    "forest": ["forest", "tree", "woods", "jungle", "nature", "garden"],
    "space": ["space", "galaxy", "cosmos", "planet", "stars", "astronaut", "nebula"],
    "desert": ["desert", "sand", "dune", "arid", "sahara"],
    "snow": ["snow", "winter", "ice", "frost", "blizzard", "arctic"],
    "rain": ["rain", "storm", "wet", "thunder", "lightning"],
    "sunset": ["sunset", "sunrise", "golden hour", "dusk", "dawn"],
    "portrait": ["portrait", "face", "person", "woman", "man", "character"],
    "animal": ["dog", "cat", "bird", "horse", "lion", "tiger", "wildlife", "animal"],
    "food": ["food", "meal", "restaurant", "cooking", "dish", "cuisine"],
}

MOOD_COLORS: dict[str, str] = {
    "ocean": "0x1E88E5", "mountain": "0x546E7A", "city": "0x37474F",
    "forest": "0x2E7D32", "space": "0x0D1B2A", "desert": "0xD4A574",
    "snow": "0xB0BEC5", "rain": "0x455A64", "sunset": "0xFF7043",
    "portrait": "0x5D4037", "animal": "0x558B2F", "food": "0xE65100",
    "default": "0x263238",
}

MOTION_FRAMES = [
    "wide establishing shot, action about to begin, anticipation, {base}",
    "subject begins moving, dynamic motion blur, tracking shot, {base}",
    "mid-action peak moment, fast movement, kinetic energy, {base}",
    "continued motion from side angle, parallax feel, {base}",
    "close-up during action, shallow depth of field, motion streaks, {base}",
    "action climax, dramatic movement, cinematic motion, {base}",
]

MOTION_QUALITY = "photorealistic, cinematic lighting, 4k, high detail, alive scene, natural movement"

CAMERA_MOTIONS = [
    "zoompan=z='1.08+0.04*sin(2*PI*on/{d})':d={d}:x='iw/2-(iw/zoom/2)+40*sin(2*PI*on/{d})':y='ih/2-(ih/zoom/2)+20*cos(2*PI*on/{d})':s={w}x{h}:fps={fps}",
    "zoompan=z='min(1.2,1.05+on*0.002)':d={d}:x='iw/2-(iw/zoom/2)-on*3':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}",
    "zoompan=z='min(1.2,1.05+on*0.002)':d={d}:x='iw/2-(iw/zoom/2)+on*3':y='ih/2-(ih/zoom/2)-on*0.5':s={w}x{h}:fps={fps}",
    "zoompan=z='1.1+0.08*sin(PI*on/{d})':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)+on*2':s={w}x{h}:fps={fps}",
    "zoompan=z='1.15-0.05*on/{d}':d={d}:x='iw/2-(iw/zoom/2)+25*sin(3*PI*on/{d})':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}",
    "zoompan=z='1.05+0.1*on/{d}':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)+15*sin(2*PI*on/{d})':s={w}x{h}:fps={fps}",
]

XFADE_TRANSITIONS = ["slideleft", "slideright", "slideup", "slidedown", "fade", "wipeleft"]


def true_video_enabled() -> bool:
    return bool(POLLINATIONS_API_KEY)


def resolve_pollinations_model(model_id: str | None, pollinations_model: str | None = None) -> str | None:
    if pollinations_model:
        return pollinations_model
    if model_id and model_id in STUDIO_VIDEO_MODELS:
        return STUDIO_VIDEO_MODELS[model_id]
    return None


def _aspect_ratio(width: int, height: int) -> str:
    if height > width * 1.15:
        return "9:16"
    if width > height * 1.15:
        return "16:9"
    return "1:1"


def _snap_duration(model: str, duration: float) -> int:
    d = int(round(duration))
    if model == "veo":
        return min([4, 6, 8], key=lambda x: abs(x - d))
    return max(2, min(d, 10))


def analyze_prompt(prompt: str) -> dict:
    text = (prompt or "").strip()
    lower = text.lower()
    tags: list[str] = []
    for scene, keywords in SCENE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            tags.append(scene)
    if not tags:
        tags = ["default"]
    mood = tags[0]
    enhanced = f"{text}, {MOTION_QUALITY}" if text else MOTION_QUALITY
    motion_shots = [
        tpl.format(base=f"{text}, {MOTION_QUALITY}") if text else tpl.format(base=MOTION_QUALITY)
        for tpl in MOTION_FRAMES
    ]
    return {
        "raw": text,
        "tags": tags,
        "mood": mood,
        "color": MOOD_COLORS.get(mood, MOOD_COLORS["default"]),
        "enhanced": enhanced,
        "motion_shots": motion_shots,
    }


def _sanitize_ffmpeg_text(text: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9 \-_,.!?']", " ", text or "")
    return cleaned.strip()[:max_len] or "AI Generated"


def _cache_path(key: str, ext: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:20]
    return CACHE_DIR / f"{digest}{ext}"


def _run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-800:] if result.stderr else "ffmpeg failed")


def _scene_overlay_filter(mood: str) -> str:
    if mood == "rain":
        return ",noise=alls=20:allf=t+u"
    if mood == "city":
        return ",eq=brightness='0.05*sin(2*PI*t*2)':contrast=1.05"
    if mood == "snow":
        return ",noise=alls=8:allf=t+u,eq=brightness=0.02"
    return ",eq=saturation='1.0+0.05*sin(2*PI*t)'"


def _is_video_bytes(data: bytes) -> bool:
    if len(data) < 50_000:
        return False
    if data[:1] == b"{" or data[:4] == b"<!DO":
        return False
    # MP4 ftyp box
    return b"ftyp" in data[:32] or data[4:8] == b"ftyp"


async def fetch_ai_image(prompt: str, width: int, height: int, seed: int | None = None) -> bytes | None:
    seed = seed if seed is not None else random.randint(1, 999_999)
    encoded = quote(prompt[:500])
    headers = {}
    if POLLINATIONS_API_KEY:
        headers["Authorization"] = f"Bearer {POLLINATIONS_API_KEY}"
    key_param = f"&key={POLLINATIONS_API_KEY}" if POLLINATIONS_API_KEY else ""
    urls = [
        f"https://gen.pollinations.ai/image/{encoded}?model=flux&width={width}&height={height}&seed={seed}&nologo=true{key_param}",
        f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed}&nologo=true&model=flux",
    ]
    timeout = aiohttp.ClientTimeout(total=180)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for url in urls:
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if len(data) > 5000 and data[:4] != b"<!DO" and data[:1] != b"{":
                            return data
            except Exception as exc:
                logger.debug("image fetch failed %s: %s", url[:60], exc)
    return None


async def fetch_ai_video(
    prompt: str,
    width: int,
    height: int,
    duration: float = 6.0,
    model_id: str | None = None,
    pollinations_model: str | None = None,
) -> tuple[bytes | None, str | None]:
    """
    Generate true AI video via Pollinations gen.pollinations.ai/video API.
    Returns (video_bytes, model_used).
    """
    if not POLLINATIONS_API_KEY:
        return None, None

    encoded = quote(prompt[:400])
    aspect = _aspect_ratio(width, height)
    primary = resolve_pollinations_model(model_id, pollinations_model)
    models_to_try: list[str] = []
    if primary:
        models_to_try.append(primary)
    for m in POLLINATIONS_FALLBACK_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    headers = {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}
    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for model in models_to_try:
            dur = _snap_duration(model, duration)
            url = (
                f"https://gen.pollinations.ai/video/{encoded}"
                f"?model={model}&duration={dur}&aspectRatio={quote(aspect)}"
                f"&nologo=true&key={POLLINATIONS_API_KEY}"
            )
            if model == "veo":
                url += "&audio=false"
            try:
                logger.info("Pollinations video request model=%s duration=%s", model, dur)
                async with session.get(url, headers=headers) as resp:
                    data = await resp.read()
                    if resp.status == 200 and _is_video_bytes(data):
                        logger.info("Pollinations video OK model=%s bytes=%s", model, len(data))
                        return data, model
                    err = data[:300].decode("utf-8", errors="replace")
                    logger.warning("Pollinations video failed model=%s status=%s body=%s", model, resp.status, err)
            except Exception as exc:
                logger.warning("Pollinations video error model=%s: %s", model, exc)
    return None, None


async def _fetch_frame(prompt: str, w: int, h: int, seed: int, analysis: dict, out: Path) -> None:
    if out.exists() and out.stat().st_size > 5000:
        return
    data = await fetch_ai_image(prompt, w, h, seed)
    if data:
        out.write_bytes(data)
    else:
        _generate_fallback_image(analysis, w, h, out)


def _generate_fallback_image(analysis: dict, width: int, height: int, out: Path) -> None:
    color = analysis["color"]
    tags = ", ".join(analysis["tags"][:3])
    prompt = _sanitize_ffmpeg_text(analysis["raw"], 60)
    vf = (
        f"drawbox=x=0:y=0:w=iw:h=ih:color={color}@0.85:t=fill,"
        f"drawtext=text='{tags}':fontsize=28:fontcolor=white:x=(w-text_w)/2:y=h*0.25,"
        f"drawtext=text='{prompt}':fontsize=18:fontcolor=white@0.9:x=(w-text_w)/2:y=h*0.5"
    )
    _run_ffmpeg([
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:d=1",
        "-vf", vf, "-frames:v", "1", str(out),
    ])


async def generate_prompt_image(prompt: str, width: int, height: int, seed: int | None = None) -> Path:
    analysis = analyze_prompt(prompt)
    cache = _cache_path(f"img:v2:{analysis['enhanced']}:{width}x{height}:{seed}", ".png")
    if cache.exists() and cache.stat().st_size > 5000:
        return cache
    w, h = max(256, min(width, 1536)), max(256, min(height, 1536))
    data = await fetch_ai_image(analysis["enhanced"], w, h, seed)
    tmp = cache.with_suffix(".tmp.png")
    if data:
        tmp.write_bytes(data)
    else:
        _generate_fallback_image(analysis, w, h, tmp)
    tmp.replace(cache)
    return cache


async def _build_motion_segments(
    frame_paths: list[Path], frames_dir: Path, w: int, h: int, fps: int, seg_duration: float, mood: str,
) -> list[Path]:
    segments: list[Path] = []
    d = int(fps * seg_duration)
    for i, fp in enumerate(frame_paths):
        seg = frames_dir / f"seg_{i:03d}.mp4"
        if seg.exists() and seg.stat().st_size > 10_000:
            segments.append(seg)
            continue
        cam = CAMERA_MOTIONS[i % len(CAMERA_MOTIONS)].format(d=d, w=w, h=h, fps=fps)
        vf = cam + _scene_overlay_filter(mood)
        _run_ffmpeg([
            "ffmpeg", "-y", "-loop", "1", "-i", str(fp),
            "-vf", vf, "-t", str(seg_duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-movflags", "+faststart", str(seg),
        ])
        segments.append(seg)
    return segments


def _concat_with_motion_transitions(segments: list[Path], out: Path, seg_duration: float, fps: int) -> None:
    import shutil
    if len(segments) == 1:
        shutil.copy(segments[0], out)
        return
    xfade_dur = 0.18
    inputs: list[str] = []
    for seg in segments:
        inputs.extend(["-i", str(seg)])
    filters: list[str] = []
    prev = "[0:v]"
    offset = seg_duration - xfade_dur
    for i in range(1, len(segments)):
        trans = XFADE_TRANSITIONS[(i - 1) % len(XFADE_TRANSITIONS)]
        out_label = f"[v{i}]" if i < len(segments) - 1 else "[vout]"
        filters.append(f"{prev}[{i}:v]xfade=transition={trans}:duration={xfade_dur}:offset={offset:.3f}{out_label}")
        prev = out_label
        offset += seg_duration - xfade_dur
    filters.append("[vout]scale=trunc(iw/2)*2:trunc(ih/2)*2[vfinal]")
    _run_ffmpeg([
        "ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", "[vfinal]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-movflags", "+faststart", str(out),
    ])


async def _generate_motion_fallback_video(
    prompt: str, w: int, h: int, duration: float, fps: int, seed: int, analysis: dict, cache: Path,
) -> Path:
    frames_dir = CACHE_DIR / f"motion_{hashlib.md5(prompt.encode()).hexdigest()[:12]}"
    frames_dir.mkdir(exist_ok=True)
    shots = analysis["motion_shots"]
    seg_duration = max(0.45, min(0.85, duration / len(shots)))
    frame_paths: list[Path] = []
    tasks = []
    for i, shot in enumerate(shots):
        fp = frames_dir / f"frame_{i:02d}.png"
        frame_paths.append(fp)
        tasks.append(_fetch_frame(shot, w, h, seed + i * 37, analysis, fp))
    await asyncio.gather(*tasks)
    segments = await _build_motion_segments(frame_paths, frames_dir, w, h, fps, seg_duration, analysis["mood"])
    tmp_out = frames_dir / "final.mp4"
    _concat_with_motion_transitions(segments, tmp_out, seg_duration, fps)
    tmp_out.replace(cache)
    _assert_playable_video(cache)
    return cache


async def generate_prompt_video(
    prompt: str,
    width: int,
    height: int,
    duration: float = 6.0,
    fps: int = 24,
    seed: int | None = None,
    model_id: str | None = None,
    pollinations_model: str | None = None,
    allow_motion_fallback: bool = True,
) -> Path:
    """True AI video via Pollinations when keyed; else multi-frame motion synthesis."""
    analysis = analyze_prompt(prompt)
    cache = _cache_path(
        f"vid:v4:{model_id}:{pollinations_model}:{analysis['enhanced']}:{width}x{height}:{duration}:{seed}",
        ".mp4",
    )
    if cache.exists() and cache.stat().st_size > 100_000:
        return cache

    w = max(512, min(width, 1280))
    h = max(512, min(height, 1280))
    base_seed = seed if seed is not None else random.randint(1, 999_999)

    if POLLINATIONS_API_KEY:
        vid_data, used_model = await fetch_ai_video(
            analysis["raw"] or analysis["enhanced"],
            w, h, duration,
            model_id=model_id,
            pollinations_model=pollinations_model,
        )
        if vid_data:
            cache.write_bytes(vid_data)
            meta_path = cache.with_suffix(".json")
            meta_path.write_text(json.dumps({"engine": "pollinations", "model": used_model}))
            return cache
        logger.warning("Pollinations video failed")
        if not allow_motion_fallback:
            raise RuntimeError("Pollinations video generation failed")

    if not allow_motion_fallback:
        raise RuntimeError("Pollinations API key not configured")

    return await _generate_motion_fallback_video(prompt, w, h, duration, fps, base_seed, analysis, cache)


async def download_source_media(url: str, suffix: str = ".mp4") -> Path:
    dest = CACHE_DIR / f"src_{hashlib.md5(url.encode()).hexdigest()[:16]}{suffix}"
    if dest.exists() and dest.stat().st_size > 10_000:
        if suffix == ".mp4":
            probe_video(dest)
        return dest
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
    if len(data) < 10_000 and suffix == ".mp4":
        raise RuntimeError(f"Downloaded source video too small ({len(data)} bytes)")
    dest.write_bytes(data)
    if suffix == ".mp4":
        probe_video(dest)
    return dest


def probe_video(path: Path) -> dict:
    import json as _json

    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = _json.loads(result.stdout)
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration") or 6.0)
    rate = video_stream.get("r_frame_rate", "24/1")
    if "/" in rate:
        num, den = rate.split("/", 1)
        fps = max(1, int(int(num) / max(int(den), 1)))
    else:
        fps = int(float(rate or 24))
    return {
        "duration": max(0.5, duration),
        "width": int(video_stream.get("width") or 640),
        "height": int(video_stream.get("height") or 360),
        "fps": fps,
        "has_audio": audio_stream is not None,
    }


def _assert_playable_video(path: Path, min_duration: float = 0.5) -> None:
    info = probe_video(path)
    if info["duration"] < min_duration:
        raise RuntimeError(f"Output video too short ({info['duration']:.2f}s)")
    if path.stat().st_size < 2000:
        raise RuntimeError(f"Output file missing or corrupt ({path.stat().st_size} bytes)")


def extract_keyframes(video: Path, count: int, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_video(video)
    duration = probe["duration"]
    frames: list[Path] = []
    for i in range(count):
        ts = min(max(0.1, (duration / (count + 1)) * (i + 1)), max(0.2, duration - 0.1))
        out = out_dir / f"kf_{i:03d}.png"
        if not out.exists() or out.stat().st_size < 1000:
            _run_ffmpeg([
                "ffmpeg", "-y", "-ss", str(ts), "-i", str(video),
                "-frames:v", "1", "-q:v", "2", str(out),
            ])
        frames.append(out)
    return frames


def analyze_uploaded_video(video_path: Path) -> dict:
    probe = probe_video(video_path)
    key_dir = CACHE_DIR / f"kf_{hashlib.md5(str(video_path).encode()).hexdigest()[:12]}"
    keyframes = extract_keyframes(video_path, 6, key_dir)
    return {**probe, "keyframes": keyframes}


def merge_prompt_with_video_analysis(prompt: str, video_info: dict) -> dict:
    text = analyze_prompt(prompt)
    duration = round(float(video_info.get("duration", 0)), 1)
    width = int(video_info.get("width", 0))
    height = int(video_info.get("height", 0))
    base = text["raw"] or "reference video content"
    context = (
        f"Based on uploaded reference video ({duration}s, {width}x{height}). "
        f"Preserve subjects, action, and composition from the source. {base}"
    )
    motion_shots = [
        tpl.format(base=f"{base}, same scene as reference video frame {i + 1}, {MOTION_QUALITY}")
        for i, tpl in enumerate(MOTION_FRAMES)
    ]
    return {
        **text,
        "enhanced": f"{context}, {MOTION_QUALITY}",
        "motion_shots": motion_shots,
        "source_video": video_info,
    }


async def _build_source_video_output(
    src: Path,
    video_info: dict,
    w: int,
    h: int,
    fps: int,
    duration: float,
    analysis: dict,
) -> Path:
    """Encode uploaded source video with light grading — keeps visuals and original audio."""
    work = CACHE_DIR / f"srcout_{hashlib.md5(str(src).encode()).hexdigest()[:12]}"
    work.mkdir(exist_ok=True)
    out = work / "styled.mp4"
    src_duration = float(video_info["duration"])
    out_duration = min(max(2.0, duration), src_duration, 15.0)
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"eq=saturation=1.12:contrast=1.04:brightness=0.02"
    )
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", str(src),
        "-t", f"{out_duration:.3f}",
        "-vf", vf,
        "-r", str(max(12, min(fps, 30))),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "medium", "-crf", "20", "-g", "30",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out),
    ])
    _assert_playable_video(out)
    return out


async def _build_source_video_segments(
    src: Path,
    video_info: dict,
    w: int,
    h: int,
    fps: int,
    duration: float,
    analysis: dict,
) -> Path:
    """Highlight reel from source clips when a single pass is not enough."""
    segment_count = min(4, max(2, int(duration / 2)))
    src_duration = float(video_info["duration"])
    seg_duration = min(max(1.0, duration / segment_count), src_duration / segment_count, 3.0)
    work = CACHE_DIR / f"srcseg_{hashlib.md5(str(src).encode()).hexdigest()[:12]}"
    work.mkdir(exist_ok=True)
    segments: list[Path] = []
    for i in range(segment_count):
        start = min((src_duration / (segment_count + 1)) * (i + 1), max(0.0, src_duration - seg_duration))
        seg = work / f"clip_{i:03d}.mp4"
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"eq=saturation=1.12:contrast=1.05:brightness=0.03"
        )
        _run_ffmpeg([
            "ffmpeg", "-y", "-ss", str(start), "-i", str(src), "-t", str(seg_duration),
            "-vf", vf,
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20", "-g", "30",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            "-movflags", "+faststart",
            str(seg),
        ])
        _assert_playable_video(seg, min_duration=0.3)
        segments.append(seg)

    list_file = work / "concat.txt"
    list_file.write_text("\n".join(f"file '{s.resolve().as_posix()}'" for s in segments))
    merged = work / "merged.mp4"
    _run_ffmpeg([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(merged),
    ])
    _assert_playable_video(merged)
    return merged


async def _generate_from_source_image(
    image_path: Path,
    prompt: str,
    w: int,
    h: int,
    duration: float,
    fps: int,
    seed: int,
    analysis: dict,
    cache: Path,
) -> Path:
    work = CACHE_DIR / f"img2vid_{hashlib.md5(str(image_path).encode()).hexdigest()[:12]}"
    work.mkdir(exist_ok=True)
    base_frame = work / "source.png"
    if not base_frame.exists():
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", str(image_path),
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
            str(base_frame),
        ])
    shots = analysis["motion_shots"]
    seg_duration = max(0.45, min(0.85, duration / len(shots)))
    frame_paths = [base_frame for _ in shots]
    segments = await _build_motion_segments(frame_paths, work, w, h, fps, seg_duration, analysis["mood"])
    tmp_out = work / "final.mp4"
    _concat_with_motion_transitions(segments, tmp_out, seg_duration, fps)
    tmp_out.replace(cache)
    return cache


async def generate_video_from_source(
    source_url: str,
    prompt: str,
    width: int,
    height: int,
    duration: float = 6.0,
    fps: int = 24,
    seed: int | None = None,
    model_id: str | None = None,
    pollinations_model: str | None = None,
    source_type: str = "video",
) -> Path:
    """Generate output guided by an uploaded source video/image plus the text prompt."""
    cache = _cache_path(
        f"srcvid:v3:{source_type}:{source_url}:{prompt}:{width}x{height}:{duration}:{seed}",
        ".mp4",
    )
    if cache.exists() and cache.stat().st_size > 5000:
        try:
            _assert_playable_video(cache)
            return cache
        except RuntimeError:
            cache.unlink(missing_ok=True)

    w = max(640, min(width, 1280))
    h = max(360, min(height, 1280))
    base_seed = seed if seed is not None else random.randint(1, 999_999)
    suffix = ".png" if source_type == "image" else ".mp4"
    src = await download_source_media(source_url, suffix=suffix)

    if source_type == "image":
        analysis = merge_prompt_with_video_analysis(prompt, {"duration": duration, "width": w, "height": h, "keyframes": []})
        return await _generate_from_source_image(src, prompt, w, h, duration, fps, base_seed, analysis, cache)

    video_info = analyze_uploaded_video(src)
    analysis = merge_prompt_with_video_analysis(prompt, video_info)
    out_duration = min(duration, float(video_info["duration"]), 15.0)

    try:
        styled = await _build_source_video_output(src, video_info, w, h, fps, out_duration, analysis)
    except Exception as exc:
        logger.warning("Full-source encode failed, trying highlight reel: %s", exc)
        styled = await _build_source_video_segments(src, video_info, w, h, fps, out_duration, analysis)

    styled.replace(cache)
    logger.info(
        "Built video from uploaded source clips prompt=%r duration=%s",
        prompt[:80],
        out_duration,
    )
    return cache


async def generate_prompt_audio(prompt: str, duration: float = 3.0) -> Path:
    analysis = analyze_prompt(prompt)
    cache = _cache_path(f"aud:{analysis['mood']}:{duration}", ".mp3")
    if cache.exists() and cache.stat().st_size > 1000:
        return cache
    if POLLINATIONS_API_KEY:
        encoded = quote((prompt or "ambient music")[:200])
        url = f"https://gen.pollinations.ai/audio/{encoded}?model=elevenmusic&duration={int(min(duration, 30))}&instrumental=true&key={POLLINATIONS_API_KEY}"
        headers = {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if len(data) > 1000 and data[:1] != b"{":
                            cache.write_bytes(data)
                            return cache
        except Exception:
            pass
    freq = {"ocean": 220, "mountain": 196, "city": 330, "forest": 262, "space": 110, "sunset": 247}.get(analysis["mood"], 440)
    _run_ffmpeg([
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
        "-c:a", "libmp3lame", "-q:a", "4", str(cache),
    ])
    return cache
