import type { AspectRatio } from '@/types/editor'

interface TopBarProps {
  currentProjectName: string
  playbackTimeSec: number
  totalDurationSec: number
  aspectRatio: AspectRatio
  onAspectRatioChange: (ratio: AspectRatio) => void
}

function formatTime(valueSec: number): string {
  const min = Math.floor(valueSec / 60)
  const sec = Math.floor(valueSec % 60)
  return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

export function TopBar({
  currentProjectName,
  playbackTimeSec,
  totalDurationSec,
  aspectRatio,
  onAspectRatioChange,
}: TopBarProps) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Editor Workspace</p>
        <h1>{currentProjectName}</h1>
      </div>

      <div className="topbar-controls">
        <div className="timer-chip">
          {formatTime(playbackTimeSec)} / {formatTime(totalDurationSec)}
        </div>

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
      </div>
    </header>
  )
}
