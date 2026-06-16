import type { AspectRatio, Asset, TimelineClip } from '@/types/editor'

interface PreviewCanvasProps {
  aspectRatio: AspectRatio
  activeClip: TimelineClip | null
  activeAsset: Asset | null
}

const ratioToPadding: Record<AspectRatio, string> = {
  '16:9': '56.25%',
  '9:16': '177.78%',
  '1:1': '100%',
}

export function PreviewCanvas({ aspectRatio, activeClip, activeAsset }: PreviewCanvasProps) {
  return (
    <section className="panel canvas-panel">
      <div className="panel-header">
        <h2>Canvas Preview</h2>
        <span className="chip">{aspectRatio}</span>
      </div>

      <div className="canvas-shell" style={{ paddingTop: ratioToPadding[aspectRatio] }}>
        <div className="canvas-content">
          <p className="canvas-kicker">Now Editing</p>
          <h3>{activeClip?.label ?? 'Select a clip from the timeline'}</h3>
          <p>{activeAsset ? `${activeAsset.name} (${activeAsset.type})` : 'No asset selected'}</p>
          <div className="canvas-overlay-grid" />
        </div>
      </div>
    </section>
  )
}
