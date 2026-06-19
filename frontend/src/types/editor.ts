export type AspectRatio = '16:9' | '9:16' | '1:1'

export interface Project {
  id: string
  name: string
  updatedAt: string
  status: 'draft' | 'rendering' | 'completed'
}

export interface Asset {
  id: string
  name: string
  type: 'image' | 'video' | 'audio'
  durationSec: number
  thumbnail: string
}

export interface TimelineClip {
  id: string
  assetId: string
  label: string
  track: 'video' | 'audio'
  startSec: number
  lengthSec: number
}

export interface GenerationJob {
  id: string
  prompt: string
  durationSec: number
  style: string
  status: 'pending' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
  progress: number
  outputUrl?: string | null
  errorMessage?: string | null
  createdAt: string
  modelId?: string
  outputKind?: 'video' | 'image' | 'audio'
}
