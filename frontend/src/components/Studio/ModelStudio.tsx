import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { GenerationJob } from '@/types/editor'
import type { ModelCategory, StudioModel } from '@/types/models'
import { CATEGORY_ICONS } from '@/types/models'
import { DEFAULT_MODEL_BY_MODE, VIDEO_GEN_MODES, type VideoGenMode } from '@/types/videoModes'
import { clearGenerations, createGeneration, downloadYouTubeAsset, listModels, uploadAsset, type BackendAsset, type BackendGeneration } from '@/services/api'

import { PromptTextarea, type PromptTextareaHandle } from './PromptTextarea'

const MAX_NUM_FRAMES = 192
/** Match backend COMFYUI_TIMEOUT (3 min) + 60s buffer */
const GENERATION_TIMEOUT_MS = 4 * 60 * 1000

function isActiveStatus(status: GenerationJob['status']): boolean {
  return status === 'pending' || status === 'queued' || status === 'processing'
}

function isJobTimedOut(job: GenerationJob): boolean {
  if (!isActiveStatus(job.status) || !job.createdAtIso) return false
  return Date.now() - new Date(job.createdAtIso).getTime() > GENERATION_TIMEOUT_MS
}

function isJobFailed(job: GenerationJob | null | undefined): boolean {
  if (!job) return false
  return job.status === 'failed' || job.status === 'cancelled' || isJobTimedOut(job)
}

interface ModelStudioProps {
  jobs: GenerationJob[]
  accessToken: string | null
  onJobsRefresh: () => Promise<void>
  onClearJobs: () => void
  onGeneratingChange: (generating: boolean) => void
  isReady: boolean
}

function generationToJob(generation: BackendGeneration): GenerationJob {
  const fps = Number(generation.params?.fps ?? 8)
  const inferredDuration = generation.num_frames > 0 ? Math.max(1, Math.round(generation.num_frames / fps)) : 0
  const extra = generation.params?.extra as Record<string, unknown> | undefined
  const modelId = extra?.model_id as string | undefined
  const typeStr = String(generation.type)

  return {
    id: generation.id,
    prompt: generation.prompt ?? '(no prompt)',
    durationSec: inferredDuration,
    style: modelId?.replace(/-/g, ' ') ?? typeStr.split('_').join(' '),
    status: generation.status,
    progress: Math.max(0, Math.min(1, generation.progress ?? 0)),
    outputUrl: generation.output_url,
    errorMessage: generation.error_message,
    createdAt: generation.created_at,
    createdAtIso: generation.created_at,
    modelId,
    outputKind: typeStr.includes('audio') ? 'audio' : typeStr.includes('image') ? 'image' : 'video',
  }
}

export function ModelStudio({
  jobs,
  accessToken,
  onJobsRefresh,
  onClearJobs,
  onGeneratingChange,
  isReady,
}: ModelStudioProps) {
  const [models, setModels] = useState<StudioModel[]>([])
  const [category, setCategory] = useState<ModelCategory | 'all'>('video')
  const [selectedModelId, setSelectedModelId] = useState('ltx-video')
  const [promptDraft, setPromptDraft] = useState('')
  const [promptSeed, setPromptSeed] = useState('')
  const promptControlRef = useRef<PromptTextareaHandle>(null)
  const [durationSec, setDurationSec] = useState(6)
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [previewJobId, setPreviewJobId] = useState<string | null>(null)
  const [uploadedAsset, setUploadedAsset] = useState<BackendAsset | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [youtubeUrl, setYoutubeUrl] = useState('')
  const [videoMode, setVideoMode] = useState<VideoGenMode>('t2v')
  const uploadInputRef = useRef<HTMLInputElement>(null)

  const handlePromptTextChange = useCallback((text: string) => {
    setPromptDraft(text)
  }, [])

  useEffect(() => {
    void listModels().then(setModels).catch(console.error)
  }, [])

  const selectedModel = useMemo(
    () => models.find(m => m.id === selectedModelId) ?? models.find(m => m.category === 'video') ?? models[0] ?? null,
    [models, selectedModelId],
  )

  const isVideoModel = selectedModel?.category === 'video'

  const filteredModels = useMemo(() => {
    let list = category === 'all' ? models : models.filter(m => m.category === category)
    if (isVideoModel) {
      if (videoMode === 't2v') {
        list = list.filter(m => m.generation_type === 'text_to_video')
      } else if (videoMode === 'i2v') {
        list = list.filter(m => m.generation_type === 'image_to_video')
      } else {
        list = list.filter(m => m.category === 'video')
      }
    }
    return list
  }, [models, category, videoMode, isVideoModel])

  useEffect(() => {
    if (!isVideoModel) return
    const preferred = DEFAULT_MODEL_BY_MODE[videoMode]
    if (models.some(m => m.id === preferred)) {
      setSelectedModelId(preferred)
    } else if (filteredModels.length > 0 && !filteredModels.some(m => m.id === selectedModelId)) {
      setSelectedModelId(filteredModels[0].id)
    }
    if (videoMode === 't2v') {
      setUploadedAsset(null)
      setYoutubeUrl('')
    } else if (videoMode === 'i2v' && uploadedAsset?.type === 'video') {
      setUploadedAsset(null)
      setYoutubeUrl('')
    } else if (videoMode === 'v2v' && uploadedAsset?.type === 'image') {
      setUploadedAsset(null)
    }
  }, [videoMode, isVideoModel, models, filteredModels, selectedModelId, uploadedAsset?.type])

  const previewJob = useMemo(() => {
    if (previewJobId) {
      const selected = jobs.find(j => j.id === previewJobId)
      if (selected) return selected
    }
    return jobs[0] ?? null
  }, [jobs, previewJobId])

  async function handleUploadFile(file: File) {
    if (videoMode === 'i2v' && !file.type.startsWith('image/')) {
      setUploadError('Image-to-Video requires an image file (.jpg, .png, .webp).')
      return
    }
    if (videoMode === 'v2v' && !file.type.startsWith('video/')) {
      setUploadError('Video-to-Video requires a video file (.mp4, .webm, etc.).')
      return
    }
    if (!isVideoModel && !file.type.startsWith('video/')) {
      setUploadError('Please upload a video file (.mp4, .webm, etc.).')
      return
    }
    setIsUploading(true)
    setUploadError(null)
    try {
      const asset = await uploadAsset(accessToken ?? '', file)
      setUploadedAsset(asset)
      setYoutubeUrl('')
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setIsUploading(false)
    }
  }

  async function handleYouTubeDownload() {
    const url = youtubeUrl.trim()
    if (!url) {
      setUploadError('Paste a YouTube link first.')
      return
    }
    setIsUploading(true)
    setUploadError(null)
    try {
      const asset = await downloadYouTubeAsset(accessToken ?? '', url)
      setUploadedAsset(asset)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'YouTube download failed')
    } finally {
      setIsUploading(false)
    }
  }

  async function handleGenerate() {
    const promptText = (promptControlRef.current?.getValue() ?? promptDraft).trim()
    if (!selectedModel || !promptText) return
    if (isVideoModel && videoMode === 'i2v' && (!uploadedAsset || uploadedAsset.type !== 'image')) {
      setError('Upload an image for Image-to-Video generation.')
      return
    }
    if (isVideoModel && videoMode === 'v2v' && (!uploadedAsset || uploadedAsset.type !== 'video')) {
      setError('Upload a video (or download from YouTube) for Video-to-Video generation.')
      return
    }
    setPromptDraft(promptText)
    onClearJobs()
    setPreviewJobId(null)
    setIsGenerating(true)
    onGeneratingChange(true)
    setError(null)
    try {
      await clearGenerations(accessToken)
      const created = await createGeneration(accessToken, {
        model_id: selectedModel.id,
        prompt: promptText,
        clear_previous: true,
        source_asset_id: isVideoModel && videoMode !== 't2v' ? uploadedAsset?.id : undefined,
        params: {
          fps: modelFps,
          num_frames: Math.min(MAX_NUM_FRAMES, Math.max(8, durationSec * modelFps)),
          width: selectedModel.category === 'video' ? 1280 : 1024,
          height: selectedModel.category === 'video' ? 720 : 1024,
          extra: { model_id: selectedModel.id, visual_theme: selectedModel.preset.visual_theme },
        },
      })
      setPreviewJobId(created.id)
      await onJobsRefresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed')
    } finally {
      setIsGenerating(false)
      onGeneratingChange(false)
    }
  }

  const categories: Array<ModelCategory | 'all'> = ['video', 'image', 'audio', 'all']
  const modelFps = Number(selectedModel?.preset.fps ?? 12)
  const maxDurationSec = isVideoModel ? Math.min(12, Math.floor(MAX_NUM_FRAMES / Math.max(modelFps, 1))) : 12
  const hasSourceVideo = uploadedAsset?.type === 'video'
  const hasSourceImage = uploadedAsset?.type === 'image'
  const activeModeHint = VIDEO_GEN_MODES.find(m => m.id === videoMode)?.hint ?? ''
  const needsUpload = isVideoModel && videoMode !== 't2v'
  const canGenerate =
    !isGenerating &&
    isReady &&
    promptDraft.trim() &&
    (!isVideoModel ||
      videoMode === 't2v' ||
      (videoMode === 'i2v' && hasSourceImage) ||
      (videoMode === 'v2v' && hasSourceVideo))
  const previewFailed = isJobFailed(previewJob)
  const previewTimedOut = previewJob ? isJobTimedOut(previewJob) : false
  const showLoading =
    !previewFailed &&
    (isGenerating ||
      previewJob?.status === 'processing' ||
      previewJob?.status === 'queued' ||
      previewJob?.status === 'pending')
  const showEmpty = !showLoading && !previewFailed && !previewJob?.outputUrl

  return (
    <div className="studio">
      <div className="studio-layout studio-layout--create-first">
        <main className="studio-workspace">
          <section className="panel studio-prompt studio-prompt--primary">
            <div className="panel-header">
              <div>
                <h2>Create</h2>
                <p className="panel-subtitle">
                  {isVideoModel
                    ? activeModeHint
                    : hasSourceVideo
                      ? 'Your uploaded video will be used — the prompt guides the edit'
                      : 'Upload a file or paste a YouTube link, then add a prompt'}
                </p>
              </div>
              {selectedModel ? <span className="chip chip--model">{selectedModel.name}</span> : null}
            </div>

            <form
              className="gen-form"
              onSubmit={event => {
                event.preventDefault()
                void handleGenerate()
              }}
            >
              {isVideoModel ? (
                <div className="studio-video-modes">
                  <span className="studio-video-modes__label">Generation type</span>
                  <div className="studio-video-modes__tabs" role="tablist" aria-label="Video generation type">
                    {VIDEO_GEN_MODES.map(mode => (
                      <button
                        key={mode.id}
                        type="button"
                        role="tab"
                        aria-selected={videoMode === mode.id}
                        className={`studio-video-mode ${videoMode === mode.id ? 'studio-video-mode--active' : ''}`}
                        onClick={() => setVideoMode(mode.id)}
                      >
                        <strong>{mode.label}</strong>
                        <span>{mode.hint}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {needsUpload ? (
              <div className="studio-upload">
                <div className="studio-upload__header">
                  <span className="prompt-label__row">
                    {videoMode === 'i2v' ? 'Source image' : 'Source video'}
                  </span>
                  <div className="studio-upload__actions">
                    <button
                      className="ghost-btn"
                      type="button"
                      disabled={isUploading || !isReady}
                      onClick={() => uploadInputRef.current?.click()}
                    >
                      {isUploading ? 'Uploading…' : uploadedAsset ? 'Replace file' : '+ Upload'}
                    </button>
                    {uploadedAsset ? (
                      <button
                        className="ghost-btn"
                        type="button"
                        onClick={() => {
                          setUploadedAsset(null)
                          setYoutubeUrl('')
                        }}
                      >
                        Remove
                      </button>
                    ) : null}
                  </div>
                </div>
                <input
                  ref={uploadInputRef}
                  className="hidden-file-input"
                  type="file"
                  accept={videoMode === 'i2v' ? 'image/*' : 'video/*'}
                  onChange={event => {
                    const file = event.target.files?.[0]
                    if (file) void handleUploadFile(file)
                    event.currentTarget.value = ''
                  }}
                />
                {uploadError ? <p className="error-text">{uploadError}</p> : null}
                {uploadedAsset ? (
                  <div className="studio-upload__preview">
                    {uploadedAsset.type === 'video' && uploadedAsset.url ? (
                      <video className="studio-upload__media" src={uploadedAsset.url} controls playsInline />
                    ) : uploadedAsset.url ? (
                      <img className="studio-upload__media" src={uploadedAsset.url} alt={uploadedAsset.filename} />
                    ) : null}
                    <p className="studio-upload__meta">
                      {uploadedAsset.filename} · {uploadedAsset.type.toUpperCase()}
                    </p>
                  </div>
                ) : (
                  <p className="prompt-hints">
                    {videoMode === 'i2v'
                      ? 'Upload a photo — the prompt describes how it should move.'
                      : 'Upload a video or download from YouTube — the prompt guides the style edit.'}
                  </p>
                )}

                {videoMode === 'v2v' ? (
                <div className="studio-youtube">
                  <label className="prompt-label__row" htmlFor="youtube-url">
                    Or paste YouTube link
                  </label>
                  <div className="studio-youtube__row">
                    <input
                      id="youtube-url"
                      className="studio-youtube__input"
                      type="url"
                      placeholder="https://www.youtube.com/watch?v=..."
                      value={youtubeUrl}
                      disabled={isUploading || !isReady}
                      onChange={event => setYoutubeUrl(event.target.value)}
                    />
                    <button
                      className="ghost-btn"
                      type="button"
                      disabled={isUploading || !isReady || !youtubeUrl.trim()}
                      onClick={() => void handleYouTubeDownload()}
                    >
                      {isUploading && youtubeUrl.trim() ? 'Downloading…' : 'Download'}
                    </button>
                  </div>
                </div>
                ) : null}
              </div>
              ) : isVideoModel && videoMode === 't2v' ? (
                <p className="prompt-hints">Text-to-Video: no upload needed — describe the scene in your prompt below.</p>
              ) : null}

              <label className="prompt-label">
                <span className="prompt-label__row">Your prompt</span>
                <PromptTextarea
                  ref={promptControlRef}
                  initialValue={promptSeed}
                  onTextChange={handlePromptTextChange}
                />
              </label>

              <div className="gen-row">
                {isVideoModel ? (
                  <label>
                    Length (seconds)
                    <input
                      type="number"
                      min={2}
                      max={maxDurationSec}
                      value={Math.min(durationSec, maxDurationSec)}
                      onChange={e => setDurationSec(Math.min(maxDurationSec, Number(e.target.value)))}
                    />
                  </label>
                ) : (
                  <div className="gen-row__spacer" />
                )}
              </div>

              <button
                className="primary-btn studio-generate-btn studio-generate-btn--large"
                type="submit"
                disabled={!canGenerate}
              >
                {isGenerating
                  ? videoMode === 't2v'
                    ? 'Generating video from prompt…'
                    : videoMode === 'i2v'
                      ? 'Animating image…'
                      : 'Processing video…'
                  : videoMode === 't2v'
                    ? 'Generate Text-to-Video'
                    : videoMode === 'i2v'
                      ? 'Generate Image-to-Video'
                      : hasSourceVideo
                        ? 'Generate Video-to-Video'
                        : `Generate ${isVideoModel ? 'Video' : selectedModel?.category === 'image' ? 'Image' : 'Audio'}`}
              </button>

              {!isReady ? <p className="prompt-hints">Connecting to backend…</p> : null}
              {error ? <p className="error-text">{error}</p> : null}
            </form>
          </section>

          <section className="panel studio-preview">
            <div className="panel-header">
              <div>
                <h2>Preview</h2>
                <p className="panel-subtitle">
                  {showLoading
                    ? 'Creating your video…'
                    : previewFailed
                      ? previewTimedOut
                        ? 'Generation timed out'
                        : 'Generation failed'
                      : previewJob?.outputUrl
                        ? 'Your latest result'
                        : 'Empty — generate a video to preview it here'}
                </p>
              </div>
              {previewJob?.outputUrl ? (
                <a className="topbar-link" href={previewJob.outputUrl} target="_blank" rel="noreferrer">
                  Download
                </a>
              ) : null}
            </div>
            <div className="studio-preview__stage">
              {showLoading ? (
                <div className="studio-preview__loading">
                  <div className="studio-preview__spinner" aria-hidden />
                  <p className="canvas-kicker">Generating</p>
                  {previewJob ? (
                    <>
                      <h3>{Math.round((previewJob.progress ?? 0) * 100)}% complete</h3>
                      <div className="job-progress__bar studio-preview__progress">
                        <span style={{ width: `${Math.max(5, (previewJob.progress ?? 0) * 100)}%` }} />
                      </div>
                    </>
                  ) : (
                    <p className="studio-preview__prompt">Starting…</p>
                  )}
                </div>
              ) : previewFailed ? (
                <div className="studio-preview__empty">
                  <div className="studio-preview__empty-icon studio-preview__empty-icon--error" aria-hidden>
                    !
                  </div>
                  <h3>{previewTimedOut ? 'Timed out' : 'Generation failed'}</h3>
                  <p className="error-text">
                    {previewJob?.errorMessage ||
                      (previewTimedOut
                        ? 'No output was produced in time. Check Docker services and try again.'
                        : 'Output could not be produced. Check worker and ComfyUI logs.')}
                  </p>
                </div>
              ) : showEmpty ? (
                <div className="studio-preview__empty">
                  <div className="studio-preview__empty-icon" aria-hidden>
                    ▶
                  </div>
                  <h3>No preview</h3>
                  <p>Enter a prompt and click Generate.</p>
                </div>
              ) : previewJob?.outputKind === 'image' ? (
                <img
                  key={previewJob.id}
                  className="studio-preview__media"
                  src={previewJob.outputUrl ?? undefined}
                  alt="Generated output"
                />
              ) : previewJob?.outputKind === 'audio' ? (
                <audio key={previewJob.id} className="studio-preview__audio" src={previewJob.outputUrl ?? undefined} controls autoPlay />
              ) : (
                <video
                  key={previewJob?.id}
                  className="studio-preview__media"
                  src={previewJob?.outputUrl ?? undefined}
                  controls
                  autoPlay
                  loop
                  playsInline
                />
              )}
            </div>
          </section>
        </main>

        <aside className="studio-sidebar">
          <section className="panel studio-models">
            <div className="panel-header">
              <h2>Model</h2>
            </div>
            <nav className="studio-tabs studio-tabs--compact">
              {categories.map(cat => (
                <button
                  key={cat}
                  type="button"
                  className={`studio-tab ${category === cat ? 'studio-tab--active' : ''}`}
                  onClick={() => setCategory(cat)}
                >
                  {cat === 'all' ? 'All' : CATEGORY_ICONS[cat]}
                </button>
              ))}
            </nav>
            <div className="model-grid model-grid--compact">
              {filteredModels.map(model => (
                <button
                  key={model.id}
                  type="button"
                  className={`model-card ${selectedModelId === model.id ? 'model-card--active' : ''}`}
                  onClick={() => setSelectedModelId(model.id)}
                >
                  <div className="model-card__top">
                    <strong>{model.name}</strong>
                    {model.badge ? <span className="model-badge">{model.badge}</span> : null}
                  </div>
                  <p className="model-card__desc">{model.description}</p>
                </button>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}

export { generationToJob }
