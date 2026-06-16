const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface BackendAsset {
  id: string
  type: 'image' | 'video' | 'audio'
  filename: string
  url: string | null
  thumbnail_url: string | null
  mime_type: string
  size_bytes: number
  width: number | null
  height: number | null
  duration_ms: number | null
  created_at: string
  updated_at: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
}

export interface UserProfile {
  id: string
  email: string
  username: string
  is_active: boolean
  avatar_url: string | null
  created_at: string
}

export interface ApiError extends Error {
  status?: number
}

export interface UploadProgress {
  loaded: number
  total: number
  progress: number
}

export type GenerationType = 'text_to_image' | 'image_to_image' | 'text_to_video' | 'image_to_video' | 'video_upscale' | 'inpaint'
export type GenerationStatus = 'pending' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'

export interface BackendGeneration {
  id: string
  owner_id: string
  project_id: string | null
  type: GenerationType
  status: GenerationStatus
  prompt: string | null
  negative_prompt: string | null
  params: Record<string, unknown>
  output_url: string | null
  thumbnail_url: string | null
  error_message: string | null
  task_id: string | null
  progress: number
  gpu_seconds: number
  width: number
  height: number
  num_frames: number
  seed: number | null
  created_at: string
  updated_at: string
}

export interface CreateGenerationPayload {
  type: GenerationType
  prompt?: string
  negative_prompt?: string
  params?: Record<string, unknown>
  project_id?: string
  source_asset_id?: string
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text()
    const error = new Error(message || response.statusText) as ApiError
    error.status = response.status
    throw error
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function getStoredAccessToken(): string | null {
  return window.localStorage.getItem('ai-video-creator.accessToken')
}

export function setStoredAccessToken(token: string | null): void {
  if (token) {
    window.localStorage.setItem('ai-video-creator.accessToken', token)
  } else {
    window.localStorage.removeItem('ai-video-creator.accessToken')
  }
}

export async function login(email: string, password: string): Promise<AuthTokens> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  return parseResponse<AuthTokens>(response)
}

export async function register(email: string, username: string, password: string): Promise<UserProfile> {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, username, password }),
  })
  return parseResponse<UserProfile>(response)
}

export async function fetchMe(token: string): Promise<UserProfile> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return parseResponse<UserProfile>(response)
}

export async function listAssets(token: string): Promise<BackendAsset[]> {
  const response = await fetch(`${API_BASE_URL}/assets/`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return parseResponse<BackendAsset[]>(response)
}

export async function listGenerations(token: string): Promise<BackendGeneration[]> {
  const response = await fetch(`${API_BASE_URL}/generations/`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return parseResponse<BackendGeneration[]>(response)
}

export async function createGeneration(
  token: string,
  payload: CreateGenerationPayload,
): Promise<BackendGeneration> {
  const response = await fetch(`${API_BASE_URL}/generations/`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return parseResponse<BackendGeneration>(response)
}

export function uploadAsset(
  token: string,
  file: File,
  projectId?: string,
  onProgress?: (progress: UploadProgress) => void,
): Promise<BackendAsset> {
  const formData = new FormData()
  formData.append('file', file)
  if (projectId) {
    formData.append('project_id', projectId)
  }

  return new Promise<BackendAsset>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/assets/upload`)
    xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    if (onProgress) {
      onProgress({ loaded: 0, total: 1, progress: 0 })
    }

    xhr.upload.onprogress = event => {
      if (!onProgress) return
      if (!event.lengthComputable) return
      onProgress({
        loaded: event.loaded,
        total: event.total,
        progress: event.total > 0 ? event.loaded / event.total : 0,
      })
    }

    xhr.onload = () => {
      if (onProgress) {
        onProgress({ loaded: 1, total: 1, progress: 1 })
      }

      const response = new Response(xhr.responseText, {
        status: xhr.status,
        statusText: xhr.statusText,
        headers: { 'Content-Type': xhr.getResponseHeader('Content-Type') ?? 'application/json' },
      })

      void parseResponse<BackendAsset>(response).then(resolve).catch(reject)
    }

    xhr.onerror = () => {
      reject(new Error('Network error during upload'))
    }

    xhr.send(formData)
  })
}
