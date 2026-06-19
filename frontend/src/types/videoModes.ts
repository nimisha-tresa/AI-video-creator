export type VideoGenMode = 't2v' | 'i2v' | 'v2v'

export const VIDEO_GEN_MODES: { id: VideoGenMode; label: string; hint: string }[] = [
  {
    id: 't2v',
    label: 'Text → Video',
    hint: 'Prompt only — AI creates all frames (5–10s local clips)',
  },
  {
    id: 'i2v',
    label: 'Image → Video',
    hint: 'Upload a photo + prompt — animate still images',
  },
  {
    id: 'v2v',
    label: 'Video → Video',
    hint: 'Upload a video + prompt — style transfer & enhancement',
  },
]

export const DEFAULT_MODEL_BY_MODE: Record<VideoGenMode, string> = {
  t2v: 'ltx-video',
  i2v: 'wan-i2v',
  v2v: 'veo-3.1',
}
