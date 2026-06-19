import { useMemo, useState } from 'react'

import type { GenerationJob } from '@/types/editor'

interface GenerationPanelProps {
  jobs: GenerationJob[]
  onQueueJob: (payload: { prompt: string; durationSec: number; style: string }) => Promise<void>
  isQueueing: boolean
  queueError: string | null
}

export function GenerationPanel({ jobs, onQueueJob, isQueueing, queueError }: GenerationPanelProps) {
  const [prompt, setPrompt] = useState('A cinematic shot of neon city streets in the rain')
  const [durationSec, setDurationSec] = useState(6)
  const [style, setStyle] = useState('Cinematic')

  const queuedCount = useMemo(() => jobs.filter(job => job.status === 'queued').length, [jobs])
  const processingCount = useMemo(() => jobs.filter(job => job.status === 'processing').length, [jobs])

  return (
    <aside className="panel generation-panel">
      <div className="panel-header">
        <h2>Generation</h2>
        <span className="chip">Queued: {queuedCount} · Processing: {processingCount}</span>
      </div>

      <form
        className="gen-form"
        onSubmit={async event => {
          event.preventDefault()
          await onQueueJob({ prompt, durationSec, style })
        }}
      >
        <label>
          Prompt
          <textarea
            value={prompt}
            onChange={event => setPrompt(event.target.value)}
            rows={4}
            required
            dir="ltr"
            lang="en"
            spellCheck
          />
        </label>

        <div className="gen-row">
          <label>
            Duration (sec)
            <input
              type="number"
              min={2}
              max={20}
              value={durationSec}
              onChange={event => setDurationSec(Number(event.target.value))}
              required
            />
          </label>

          <label>
            Style
            <select value={style} onChange={event => setStyle(event.target.value)}>
              <option value="Cinematic">Cinematic</option>
              <option value="Anime">Anime</option>
              <option value="Photoreal">Photoreal</option>
              <option value="Synthwave">Synthwave</option>
            </select>
          </label>
        </div>

        <button className="primary-btn" type="submit" disabled={isQueueing || !prompt.trim()}>
          {isQueueing ? 'Generating…' : 'Generate Video'}
        </button>

        {queueError ? <p className="error-text">{queueError}</p> : null}
      </form>

      <div className="job-list">
        {jobs.map(job => (
          <article key={job.id} className="job-card">
            <div className="job-header">
              <strong>{job.style}</strong>
              <span className={`status status-${job.status}`}>{job.status}</span>
            </div>
            <p className="job-prompt">{job.prompt}</p>
            <div className="job-progress">
              <div className="job-progress__label">{Math.round(job.progress * 100)}%</div>
              <div className="job-progress__bar">
                <span style={{ width: `${Math.max(0, Math.min(100, job.progress * 100))}%` }} />
              </div>
            </div>
            {job.outputUrl ? (
              <div className="job-output">
                <video className="job-output__video" src={job.outputUrl} controls playsInline />
                <a className="job-output-link" href={job.outputUrl} target="_blank" rel="noreferrer">
                  Download output
                </a>
              </div>
            ) : null}
            {job.errorMessage ? <p className="upload-item__error">{job.errorMessage}</p> : null}
            <p className="job-meta">
              {job.durationSec}s · {job.createdAt}
            </p>
          </article>
        ))}
      </div>
    </aside>
  )
}
