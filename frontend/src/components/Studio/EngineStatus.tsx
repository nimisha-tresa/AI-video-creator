import type { StudioConfig } from '@/services/api'

const ENGINE_LABELS: Record<string, string> = {
  'pollinations-true-video': 'Cloud AI (Pollinations)',
  'local-animatediff': 'Local AI (AnimateDiff)',
  'motion-synthesis': 'Basic fallback',
}

interface EngineStatusProps {
  config: StudioConfig | null
  collapsed: boolean
  onToggle: () => void
}

export function EngineStatus({ config, collapsed, onToggle }: EngineStatusProps) {
  const pollOk = config?.pollinations_ready
  const localOk = config?.models_ready
  const chain = config?.engine_chain ?? []
  const primary = chain[0] ? ENGINE_LABELS[chain[0]] ?? chain[0] : 'Not configured'

  const steps = [
    {
      id: 'pollinations',
      title: 'Cloud video (best quality)',
      desc: pollOk
        ? 'Connected — Veo, Seedance & Wan ready'
        : 'Add a free API key from enter.pollinations.ai',
      done: pollOk,
      optional: false,
    },
    {
      id: 'local',
      title: 'Local models (free backup)',
      desc: localOk
        ? 'Downloaded — works offline, no API cost'
        : 'Run download-local-models.ps1 (~6 GB)',
      done: localOk,
      optional: true,
    },
    {
      id: 'fallback',
      title: 'Basic fallback',
      desc: pollOk || localOk ? 'Used only if primary engines fail' : 'Active now — lower quality slideshow',
      done: pollOk || localOk,
      optional: true,
    },
  ]

  return (
    <section className={`panel engine-status ${pollOk && localOk ? 'engine-status--ready' : ''}`}>
      <div className="engine-status__header">
        <div>
          <h2 className="engine-status__title">How your videos are made</h2>
          <p className="engine-status__subtitle">
            {pollOk || localOk
              ? `Primary engine: ${primary}`
              : 'Set up one option below for true AI video'}
          </p>
        </div>
        <button type="button" className="ghost-btn engine-status__toggle" onClick={onToggle}>
          {collapsed ? 'Show setup' : 'Hide setup'}
        </button>
      </div>

      {!collapsed ? (
        <>
          <div className="engine-steps">
            {steps.map((step, i) => (
              <div
                key={step.id}
                className={`engine-step ${step.done ? 'engine-step--done' : 'engine-step--pending'}`}
              >
                <div className="engine-step__icon" aria-hidden>
                  {step.done ? '✓' : i + 1}
                </div>
                <div className="engine-step__body">
                  <strong>{step.title}</strong>
                  <p>{step.desc}</p>
                </div>
              </div>
            ))}
          </div>

          {!pollOk ? (
            <details className="engine-help">
              <summary>Step 1: Connect Pollinations (recommended)</summary>
              <ol>
                <li>
                  Create a free account at{' '}
                  <a href="https://enter.pollinations.ai" target="_blank" rel="noreferrer">
                    enter.pollinations.ai
                  </a>
                </li>
                <li>Copy your secret key (starts with <code>sk_</code>)</li>
                <li>
                  Add to <code>.env</code>: <code>POLLINATIONS_API_KEY=sk_your_key</code>
                </li>
                <li>
                  Restart: <code>docker compose -f infra/docker-compose.yml up -d comfyui worker api</code>
                </li>
              </ol>
            </details>
          ) : null}

          {!localOk ? (
            <details className="engine-help">
              <summary>Step 2: Download local models (optional, fully free)</summary>
              <p>
                In PowerShell from the project folder, run:
                <code className="engine-help__cmd">.\scripts\download-local-models.ps1</code>
              </p>
              <p className="engine-help__note">~6 GB download. Used automatically if cloud API is unavailable.</p>
            </details>
          ) : null}
        </>
      ) : (
        <div className="engine-status__pills">
          <span className={`status-pill ${pollOk ? 'status-pill--ok' : 'status-pill--warn'}`}>
            Cloud {pollOk ? '✓' : '—'}
          </span>
          <span className={`status-pill ${localOk ? 'status-pill--ok' : 'status-pill--muted'}`}>
            Local {localOk ? '✓' : '—'}
          </span>
          {chain.length > 1 ? (
            <span className="status-pill status-pill--muted">{chain.length}-step fallback</span>
          ) : null}
        </div>
      )}
    </section>
  )
}

export function estimateWaitMinutes(config: StudioConfig | null, isVideo: boolean): string {
  if (!isVideo) return 'about 30 seconds'
  if (config?.pollinations_ready) return '2–5 minutes'
  if (config?.models_ready) return '3–10 minutes'
  return '1–3 minutes (basic mode)'
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: 'Waiting',
    queued: 'In queue',
    processing: 'Creating…',
    completed: 'Done',
    failed: 'Failed',
    cancelled: 'Cancelled',
  }
  return map[status] ?? status
}
