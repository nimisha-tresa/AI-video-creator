import type { AspectRatio, Asset, TimelineClip } from '@/types/editor'

interface PreviewCanvasProps {
  aspectRatio: AspectRatio
  activeClip: TimelineClip | null
  activeAsset: Asset | null
  previewVideoUrl?: string | null
  onAspectRatioChange?: (ratio: AspectRatio) => void
}

const ratioToPadding: Record<AspectRatio, string> = {
  '16:9': '56.25%',
  '9:16': '177.78%',
  '1:1': '100%',
}

export function PreviewCanvas({
  aspectRatio,
  activeClip,
  activeAsset,
  previewVideoUrl,
  onAspectRatioChange,
}: PreviewCanvasProps) {
  return (
    <section className="panel canvas-panel">
      <div className="panel-header">
        <h2>Video Preview</h2>
        <div className="canvas-header-controls">
          {onAspectRatioChange ? (
            <label className="ratio-select-wrap">
              Aspect
              <select
                value={aspectRatio}
                onChange={event => onAspectRatioChange(event.target.value as AspectRatio)}
                className="ratio-select"
              >
                <option value="16:9">16:9</option>
                <option value="9:16">9:16</option>
                <option value="1:1">1:1</option>
              </select>
            </label>
          ) : (
            <span className="chip">{aspectRatio}</span>
          )}
        </div>
      </div>

      <div className="canvas-shell" style={{ paddingTop: ratioToPadding[aspectRatio] }}>
        {previewVideoUrl ? (
          <video
            className="canvas-video"
            src={previewVideoUrl}
            controls
            autoPlay
            loop
            muted
            playsInline
          />
        ) : (
          <div className="canvas-content">
            <p className="canvas-kicker">Ready to Generate</p>
            <h3>{activeClip?.label ?? 'Queue a prompt to create your first video'}</h3>
            <p>{activeAsset ? `${activeAsset.name} (${activeAsset.type})` : 'Enter a prompt in the Generation panel →'}</p>
            <div className="canvas-overlay-grid" />
          </div>
        )}
      </div>
    </section>
  )
}
