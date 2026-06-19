import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { GenerationJob } from '@/types/editor'
import type { ModelCategory, StudioModel } from '@/types/models'
import { CATEGORY_ICONS } from '@/types/models'
import { clearGenerations, createGeneration, listModels, uploadAsset, type BackendAsset, type BackendGeneration } from '@/services/api'

import { PromptTextarea, type PromptTextareaHandle } from './PromptTextarea'

const MAX_NUM_FRAMES = 192

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
  const [category, setCategory] = useState<ModelCategory | 'video'>('video')
  const [selectedModelId, setSelectedModelId] = useState('veo-3.1')
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
  const uploadInputRef = useRef<HTMLInputElement>(null)

  const handlePromptTextChange = useCallback((text: string) => {
    setPromptDraft(text)
  }, [])

  useEffect(() => {
    void listModels().then(setModels).catch(console.error)
  }, [])

  const filteredModels = useMemo(() => {
    if (category === 'all') return models
    return models.filter(m => m.category === category)
  }, [models, category])

  const selectedModel = useMemo(
    () => models.find(m => m.id === selectedModelId) ?? models.find(m => m.category === 'video') ?? models[0] ?? null,
    [models, selectedModelId],
  )

  const previewJob = useMemo(() => {
    if (previewJobId) {
      const selected = jobs.find(j => j.id === previewJobId)
      if (selected) return selected
    }
    return jobs[0] ?? null
  }, [jobs, previewJobId])

  async function handleUploadFile(file: File) {
    if (!file.type.startsWith('video/')) {
      setUploadError('Please upload a video file (.mp4, .webm, etc.).')
      return
    }
    setIsUploading(true)
    setUploadError(null)
    try {
      const asset = await uploadAsset(accessToken ?? '', file)
      setUploadedAsset(asset)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setIsUploading(false)
    }
  }

  async function handleGenerate() {
    const promptText = (promptControlRef.current?.getValue() ?? promptDraft).trim()
    if (!selectedModel || !promptText) return
    if (isVideoModel && !uploadedAsset) {
      setError('Upload a reference video first — generation uses your upload, not AI scenes from the prompt alone.')
      return
    }
    if (isVideoModel && uploadedAsset && uploadedAsset.type !== 'video') {
      setError('For video generation, please upload a video file (not only an image).')
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
        source_asset_id: uploadedAsset?.id,
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
  const isVideoModel = selectedModel?.category === 'video'
  const modelFps = Number(selectedModel?.preset.fps ?? 12)
  const maxDurationSec = isVideoModel ? Math.min(12, Math.floor(MAX_NUM_FRAMES / Math.max(modelFps, 1))) : 12
  const hasSourceVideo = uploadedAsset?.type === 'video'
  const showLoading =
    isGenerating || previewJob?.status === 'processing' || previewJob?.status === 'queued'
  const showEmpty = !showLoading && !previewJob?.outputUrl

  return (
    <div className="studio">
      <div className="studio-layout studio-layout--create-first">
        <main className="studio-workspace">
          <section className="panel studio-prompt studio-prompt--primary">
            <div className="panel-header">
              <div>
                <h2>Create</h2>
                <p className="panel-subtitle">
                  {hasSourceVideo
                    ? 'Your uploaded video will be used — the prompt guides the edit, not AI scene generation'
                    : 'Upload a reference video first, then add a prompt'}
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
              <div className="studio-upload">
                <div className="studio-upload__header">
                  <span className="prompt-label__row">Reference video / image</span>
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
                      <button className="ghost-btn" type="button" onClick={() => setUploadedAsset(null)}>
                        Remove
                      </button>
                    ) : null}
                  </div>
                </div>
                <input
                  ref={uploadInputRef}
                  className="hidden-file-input"
                  type="file"
                  accept="video/*"
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
                  <p className="prompt-hints">Upload a video to analyze — your prompt guides the new output.</p>
                )}
              </div>

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
                disabled={isGenerating || !isReady || !promptDraft.trim() || (isVideoModel && !uploadedAsset)}
              >
                {isGenerating
                  ? hasSourceVideo
                    ? 'Analyzing upload and generating…'
                    : `Creating your ${isVideoModel ? 'video' : 'output'}…`
                  : hasSourceVideo
                    ? 'Generate from uploaded video'
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
                  src={previewJob.outputUrl}
                  alt="Generated output"
                />
              ) : previewJob?.outputKind === 'audio' ? (
                <audio key={previewJob.id} className="studio-preview__audio" src={previewJob.outputUrl} controls autoPlay />
              ) : (
                <video
                  key={previewJob?.id}
                  className="studio-preview__media"
                  src={previewJob?.outputUrl}
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
