export type ModelCategory = 'video' | 'image' | 'audio' | 'llm'

export interface StudioModel {
  id: string
  name: string
  provider: string
  category: ModelCategory
  generation_type: string
  description: string
  badge: string | null
  compatible: boolean
  preset: {
    fps: number
    steps: number
    cfg: number
    motion_scale: number
    visual_theme: string
    duration_sec: number
  }
}

export const CATEGORY_LABELS: Record<ModelCategory, string> = {
  video: 'Video',
  image: 'Image',
  audio: 'Audio',
  llm: 'Creative',
}

export const CATEGORY_ICONS: Record<ModelCategory, string> = {
  video: '🎬',
  image: '🖼️',
  audio: '🔊',
  llm: '✨',
}
