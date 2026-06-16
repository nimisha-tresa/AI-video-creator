import { useEffect, useMemo, useState } from 'react'

import { AssetLibraryPanel } from '@/components/AssetLibrary/AssetLibraryPanel'
import { PreviewCanvas } from '@/components/Canvas/PreviewCanvas'
import { GenerationPanel } from '@/components/GenerationPanel/GenerationPanel'
import { ProjectSidebar } from '@/components/Sidebar/ProjectSidebar'
import { TimelineEditor } from '@/components/Timeline/TimelineEditor'
import { TopBar } from '@/components/ui/TopBar'
import type { AspectRatio, Asset, GenerationJob, Project, TimelineClip } from '@/types/editor'
import {
  createGeneration,
  fetchMe,
  getStoredAccessToken,
  listGenerations,
  listAssets,
  login,
  register,
  setStoredAccessToken,
  uploadAsset,
  type BackendAsset,
  type BackendGeneration,
  type UserProfile,
} from '@/services/api'

import './App.css'

const mockProjects: Project[] = [
  { id: 'p1', name: 'Summer Drop Campaign', updatedAt: '2h ago', status: 'draft' },
  { id: 'p2', name: 'Sneaker Teaser Reel', updatedAt: 'yesterday', status: 'rendering' },
  { id: 'p3', name: 'Founder Story Cut', updatedAt: '3d ago', status: 'completed' },
]

const mockAssets: Asset[] = [
  { id: 'a1', name: 'Neon Street', type: 'video', durationSec: 8, thumbnail: '🌃' },
  { id: 'a2', name: 'Hero Product', type: 'image', durationSec: 4, thumbnail: '👟' },
  { id: 'a3', name: 'City Drone', type: 'video', durationSec: 6, thumbnail: '🚁' },
  { id: 'a4', name: 'Ambient Pulse', type: 'audio', durationSec: 12, thumbnail: '🎵' },
]

const mockTimeline: TimelineClip[] = [
  { id: 'c1', assetId: 'a2', label: 'Product Reveal', track: 'video', startSec: 0, lengthSec: 4 },
  { id: 'c2', assetId: 'a1', label: 'Neon Transition', track: 'video', startSec: 4, lengthSec: 5 },
  { id: 'c3', assetId: 'a4', label: 'Ambient Track', track: 'audio', startSec: 0, lengthSec: 11 },
]

const initialJobs: GenerationJob[] = []

interface AuthState {
  email: string
  username: string
  password: string
}

interface UploadItem {
  id: string
  name: string
  progress: number
  status: 'queued' | 'uploading' | 'done' | 'error'
  error?: string
}

const DEV_AUTH = {
  email: 'demo@local.app',
  username: 'demo',
  password: 'password123',
}

function assetToFrontend(asset: BackendAsset): Asset {
  return {
    id: asset.id,
    name: asset.filename,
    type: asset.type,
    durationSec: asset.duration_ms ? Math.max(1, Math.round(asset.duration_ms / 1000)) : 0,
    thumbnail: asset.type === 'image' ? '🖼️' : asset.type === 'video' ? '🎬' : '🎵',
  }
}

function mergeBackendWithMockAssets(backendAssets: BackendAsset[], existingAssets: Asset[]): Asset[] {
  const backendMapped = backendAssets.map(assetToFrontend)
  const mockOnly = existingAssets.filter(asset => asset.id.startsWith('a'))
  return [...backendMapped, ...mockOnly]
}

function formatRelativeTime(dateIso: string): string {
  const diffMs = Date.now() - new Date(dateIso).getTime()
  const diffSec = Math.max(0, Math.round(diffMs / 1000))
  if (diffSec < 10) return 'just now'
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.round(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.round(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.round(diffHr / 24)
  return `${diffDay}d ago`
}

function generationToJob(generation: BackendGeneration): GenerationJob {
  const fps = Number(generation.params?.fps ?? 8)
  const inferredDuration = generation.num_frames > 0 ? Math.max(1, Math.round(generation.num_frames / fps)) : 0

  return {
    id: generation.id,
    prompt: generation.prompt ?? '(no prompt)',
    durationSec: inferredDuration,
    style: String(generation.type).split('_').join(' '),
    status: generation.status,
    progress: Math.max(0, Math.min(1, generation.progress ?? 0)),
    outputUrl: generation.output_url,
    errorMessage: generation.error_message,
    createdAt: formatRelativeTime(generation.created_at),
  }
}

export default function App() {
  const [selectedProjectId, setSelectedProjectId] = useState(mockProjects[0].id)
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(mockAssets[0].id)
  const [selectedClipId, setSelectedClipId] = useState<string | null>(mockTimeline[0].id)
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>('16:9')
  const [jobs, setJobs] = useState<GenerationJob[]>(initialJobs)
  const [assets, setAssets] = useState<Asset[]>(mockAssets)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadItems, setUploadItems] = useState<UploadItem[]>([])
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [authError, setAuthError] = useState<string | null>(null)
  const [generationError, setGenerationError] = useState<string | null>(null)
  const [isQueueingGeneration, setIsQueueingGeneration] = useState(false)
  const [authStatus, setAuthStatus] = useState<'booting' | 'ready'>('booting')
  const [showAuthDrawer, setShowAuthDrawer] = useState(false)
  const [user, setUser] = useState<UserProfile | null>(null)
  const [accessToken, setAccessTokenState] = useState<string | null>(getStoredAccessToken())
  const [authForm, setAuthForm] = useState<AuthState>(DEV_AUTH)

  const activeProject = useMemo(
    () => mockProjects.find(project => project.id === selectedProjectId) ?? mockProjects[0],
    [selectedProjectId],
  )

  const activeClip = useMemo(
    () => mockTimeline.find(clip => clip.id === selectedClipId) ?? null,
    [selectedClipId],
  )

  const activeAsset = useMemo(() => {
    const assetId = activeClip?.assetId ?? selectedAssetId
    return assets.find(asset => asset.id === assetId) ?? null
  }, [activeClip, assets, selectedAssetId])

  const totalDurationSec = useMemo(
    () => Math.max(...mockTimeline.map(clip => clip.startSec + clip.lengthSec)),
    [],
  )

  async function ensureUploadSession(): Promise<string | null> {
    try {
      let token = accessToken

      if (token) {
        try {
          const profile = await fetchMe(token)
          setUser(profile)
          return token
        } catch {
          token = null
          setStoredAccessToken(null)
          setAccessTokenState(null)
        }
      }

      try {
        const tokens = await login(DEV_AUTH.email, DEV_AUTH.password)
        token = tokens.access_token
      } catch {
        await register(DEV_AUTH.email, DEV_AUTH.username, DEV_AUTH.password)
        const tokens = await login(DEV_AUTH.email, DEV_AUTH.password)
        token = tokens.access_token
      }

      if (!token) return null

      setStoredAccessToken(token)
      setAccessTokenState(token)
      const profile = await fetchMe(token)
      setUser(profile)
      return token
    } catch (error) {
      console.error(error)
      setUser(null)
      setStoredAccessToken(null)
      setAccessTokenState(null)
      setAuthError('Could not create upload session. Open Sign in and try again.')
      return null
    }
  }

  async function refreshAssetsForToken(token: string) {
    try {
      const backendAssets = await listAssets(token)
      setAssets(prev => mergeBackendWithMockAssets(backendAssets, prev))
      setAuthError(null)
    } catch (error) {
      console.error(error)
      setAuthError('Connected, but failed to load existing assets.')
    }
  }

  async function refreshGenerationsForToken(token: string) {
    try {
      const backendGenerations = await listGenerations(token)
      setJobs(backendGenerations.map(generationToJob))
      setGenerationError(null)
    } catch (error) {
      console.error(error)
      setGenerationError('Failed to refresh generation status updates.')
    }
  }

  useEffect(() => {
    let mounted = true

    async function bootstrap() {
      setAuthStatus('booting')
      try {
        const token = await ensureUploadSession()
        if (!mounted || !token) return
        await refreshAssetsForToken(token)
        await refreshGenerationsForToken(token)
      } finally {
        if (mounted) setAuthStatus('ready')
      }
    }

    void bootstrap()

    return () => {
      mounted = false
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return

    const interval = window.setInterval(() => {
      void refreshGenerationsForToken(accessToken)
    }, 2500)

    return () => window.clearInterval(interval)
  }, [accessToken])

  async function handleQueueGeneration(payload: { prompt: string; durationSec: number; style: string }) {
    const token = accessToken ?? (await ensureUploadSession())
    if (!token) {
      setGenerationError('Could not create a session for generation. Please sign in and retry.')
      return
    }

    setIsQueueingGeneration(true)
    setGenerationError(null)

    try {
      await createGeneration(token, {
        type: 'text_to_video',
        prompt: payload.prompt,
        params: {
          fps: 8,
          num_frames: Math.max(8, payload.durationSec * 8),
          width: 1024,
          height: 576,
        },
      })
      await refreshGenerationsForToken(token)
    } catch (error) {
      console.error(error)
      setGenerationError(error instanceof Error ? error.message : 'Failed to queue generation')
    } finally {
      setIsQueueingGeneration(false)
    }
  }

  const playbackTimeSec = activeClip?.startSec ?? 0

  async function handleAuthenticate(mode: 'login' | 'register') {
    setAuthError(null)
    try {
      if (mode === 'login') {
        const tokens = await login(authForm.email, authForm.password)
        setStoredAccessToken(tokens.access_token)
        setAccessTokenState(tokens.access_token)
        await refreshAssetsForToken(tokens.access_token)
        setShowAuthDrawer(false)
        return
      }

      await register(authForm.email, authForm.username, authForm.password)
      const tokens = await login(authForm.email, authForm.password)
      setStoredAccessToken(tokens.access_token)
      setAccessTokenState(tokens.access_token)
      await refreshAssetsForToken(tokens.access_token)
      setShowAuthDrawer(false)
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Authentication failed')
    }
  }

  async function handlePickFiles(files: FileList) {
    const token = accessToken ?? (await ensureUploadSession())
    if (!token) {
      setAuthError('Upload session could not be started. Open Sign in and retry.')
      setShowAuthDrawer(true)
      return
    }

    setUploadError(null)
    setIsUploading(true)
    setUploadProgress(0)

    const fileList = Array.from(files)
    const initialItems: UploadItem[] = fileList.map((file, index) => ({
      id: `${Date.now()}-${index}-${file.name}`,
      name: file.name,
      progress: 0,
      status: 'queued',
    }))
    setUploadItems(prev => [...initialItems, ...prev])

    try {
      const uploadedAssets: Asset[] = []

      for (let index = 0; index < fileList.length; index += 1) {
        const file = fileList[index]
        const uploadItemId = initialItems[index]?.id

        if (uploadItemId) {
          setUploadItems(prev =>
            prev.map(item => (item.id === uploadItemId ? { ...item, status: 'uploading' } : item)),
          )
        }

        const uploaded = await uploadAsset(token, file, undefined, progress => {
          const overall = (index + progress.progress) / fileList.length
          setUploadProgress(overall)
          if (uploadItemId) {
            setUploadItems(prev =>
              prev.map(item =>
                item.id === uploadItemId
                  ? { ...item, status: 'uploading', progress: progress.progress }
                  : item,
              ),
            )
          }
        })
        uploadedAssets.push(assetToFrontend(uploaded))
        setUploadProgress((index + 1) / fileList.length)

        if (uploadItemId) {
          setUploadItems(prev =>
            prev.map(item =>
              item.id === uploadItemId ? { ...item, status: 'done', progress: 1 } : item,
            ),
          )
        }
      }

      const frontendAssets = uploadedAssets
      setAssets(prev => [...frontendAssets, ...prev])
      if (frontendAssets[0]) {
        setSelectedAssetId(frontendAssets[0].id)
      }
      await refreshAssetsForToken(token)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Upload failed'
      setUploadItems(prev =>
        prev.map(item => (item.status === 'uploading' || item.status === 'queued' ? { ...item, status: 'error', error: message } : item)),
      )
      setUploadError(error instanceof Error ? error.message : 'Upload failed')
    } finally {
      setIsUploading(false)
      setUploadProgress(0)
    }
  }

  return (
    <div className="editor-root">
      <header className="topbar">
        <h1>AI Video Creator Studio</h1>
        <div className="topbar__links">
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
            API Docs
          </a>
          <a href="http://localhost:8000/health" target="_blank" rel="noreferrer">
            API Health
          </a>
          <button className="button" type="button" onClick={() => setShowAuthDrawer(value => !value)}>
            {user ? user.username : 'Sign in'}
          </button>
        </div>
      </header>

      {showAuthDrawer ? (
        <section className="panel auth-panel">
          <div className="panel__header">
            <h2>Account</h2>
            <button className="button" type="button" onClick={() => setShowAuthDrawer(false)}>
              Close
            </button>
          </div>

          <div className="form-grid">
            <label>
              Email
              <input
                value={authForm.email}
                onChange={event => setAuthForm(prev => ({ ...prev, email: event.target.value }))}
              />
            </label>

            <label>
              Username
              <input
                value={authForm.username}
                onChange={event => setAuthForm(prev => ({ ...prev, username: event.target.value }))}
              />
            </label>

            <label>
              Password
              <input
                type="password"
                value={authForm.password}
                onChange={event => setAuthForm(prev => ({ ...prev, password: event.target.value }))}
              />
            </label>

            <div className="auth-actions">
              <button className="button button--primary" type="button" onClick={() => void handleAuthenticate('login')}>
                Login
              </button>
              <button className="button" type="button" onClick={() => void handleAuthenticate('register')}>
                Register
              </button>
            </div>

            {authError ? <p className="error-text">{authError}</p> : null}
          </div>
        </section>
      ) : null}

      <div className="workspace-grid">
        <ProjectSidebar
          projects={mockProjects}
          selectedProjectId={selectedProjectId}
          onSelectProject={setSelectedProjectId}
        />

        <main className="center-column">
          <TopBar
            currentProjectName={activeProject.name}
            playbackTimeSec={playbackTimeSec}
            totalDurationSec={totalDurationSec}
            aspectRatio={aspectRatio}
            onAspectRatioChange={setAspectRatio}
          />

          <PreviewCanvas aspectRatio={aspectRatio} activeClip={activeClip} activeAsset={activeAsset} />

          <AssetLibraryPanel
            assets={assets}
            selectedAssetId={selectedAssetId}
            onSelectAsset={setSelectedAssetId}
            isAuthenticated={Boolean(accessToken)}
            authStatus={authStatus}
            authError={authError}
            uploadError={uploadError}
            isUploading={isUploading}
            uploadProgress={uploadProgress}
            uploadItems={uploadItems}
            uploadDestination="Uploads are stored in backend object storage (MinIO bucket: assets) via /assets/upload."
            onPickFiles={handlePickFiles}
            onOpenAuth={() => setShowAuthDrawer(true)}
          />

          <TimelineEditor clips={mockTimeline} selectedClipId={selectedClipId} onSelectClip={setSelectedClipId} />
        </main>

        <GenerationPanel
          jobs={jobs}
          onQueueJob={handleQueueGeneration}
          isQueueing={isQueueingGeneration}
          queueError={generationError}
        />
      </div>
    </div>
  )
}
