import type { TimelineClip } from '@/types/editor'

interface TimelineEditorProps {
  clips: TimelineClip[]
  selectedClipId: string | null
  onSelectClip: (clipId: string) => void
}

export function TimelineEditor({ clips, selectedClipId, onSelectClip }: TimelineEditorProps) {
  return (
    <section className="panel timeline-panel">
      <div className="panel-header">
        <h2>Timeline</h2>
        <span className="chip">{clips.length} clips</span>
      </div>

      <div className="timeline-tracks">
        {clips.map(clip => (
          <button
            key={clip.id}
            type="button"
            className={`timeline-clip ${selectedClipId === clip.id ? 'active' : ''}`}
            onClick={() => onSelectClip(clip.id)}
            style={{ width: `${Math.max(clip.lengthSec * 26, 120)}px` }}
          >
            <div className="timeline-clip-title">{clip.label}</div>
            <div className="timeline-clip-meta">
              {clip.track.toUpperCase()} · {clip.startSec}s → {clip.startSec + clip.lengthSec}s
            </div>
          </button>
        ))}
      </div>
    </section>
  )
}
