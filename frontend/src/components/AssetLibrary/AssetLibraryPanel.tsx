import { useRef, type DragEvent } from 'react'

import type { Asset } from '@/types/editor'

interface UploadItem {
  id: string
  name: string
  progress: number
  status: 'queued' | 'uploading' | 'done' | 'error'
  error?: string
}

interface AssetLibraryPanelProps {
  assets: Asset[]
  selectedAssetId: string | null
  onSelectAsset: (assetId: string) => void
  isAuthenticated: boolean
  authStatus: 'booting' | 'ready'
  authError: string | null
  uploadError: string | null
  isUploading: boolean
  uploadProgress: number
  uploadItems: UploadItem[]
  uploadDestination: string
  onPickFiles: (files: FileList) => Promise<void>
  onOpenAuth: () => void
}

export function AssetLibraryPanel({
  assets,
  selectedAssetId,
  onSelectAsset,
  isAuthenticated,
  authStatus,
  authError,
  uploadError,
  isUploading,
  uploadProgress,
  uploadItems,
  uploadDestination,
  onPickFiles,
  onOpenAuth,
}: AssetLibraryPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const dragCounterRef = useRef(0)

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault()
    dragCounterRef.current = 0
    if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
      void onPickFiles(event.dataTransfer.files)
    }
  }

  return (
    <section
      className="panel asset-library"
      onDragEnter={event => {
        event.preventDefault()
        dragCounterRef.current += 1
      }}
      onDragOver={event => event.preventDefault()}
      onDragLeave={event => {
        event.preventDefault()
        dragCounterRef.current = Math.max(0, dragCounterRef.current - 1)
      }}
      onDrop={handleDrop}
    >
      <div className="panel-header">
        <h2>Asset Library</h2>
        <button
          className="ghost-btn"
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
        >
          {isUploading ? `Uploading ${Math.round(uploadProgress * 100)}%` : '+ Upload'}
        </button>
      </div>

      <p className="upload-destination">{uploadDestination}</p>

      <input
        ref={fileInputRef}
        className="hidden-file-input"
        type="file"
        accept="image/*,video/*,audio/*"
        multiple
        onChange={async event => {
          if (event.target.files && event.target.files.length > 0) {
            await onPickFiles(event.target.files)
            event.currentTarget.value = ''
          }
        }}
      />

      {authStatus === 'booting' ? (
        <div aria-hidden="true" className="silent-loader" />
      ) : !isAuthenticated ? (
        <div className="inline-banner inline-banner--warning">
          <p>
            Uploads are ready after signing in. You can also use the demo account loaded automatically in local dev.
          </p>
          <button className="button button--primary" type="button" onClick={onOpenAuth}>
            Sign in / Register
          </button>
        </div>
      ) : null}

      {authError ? <div className="inline-banner inline-banner--error">{authError}</div> : null}
      {uploadError ? <div className="inline-banner inline-banner--error">{uploadError}</div> : null}

      {isUploading ? (
        <div className="upload-progress">
          <div className="upload-progress__label">Uploading {Math.round(uploadProgress * 100)}%</div>
          <div className="upload-progress__bar">
            <span style={{ width: `${Math.max(0, Math.min(100, uploadProgress * 100))}%` }} />
          </div>
        </div>
      ) : null}

      <div className="upload-items">
        {uploadItems.map(item => (
          <article key={item.id} className={`upload-item upload-item--${item.status}`}>
            <div className="upload-item__top">
              <strong>{item.name}</strong>
              <span>{Math.round(item.progress * 100)}%</span>
            </div>
            <div className="upload-item__bar">
              <span style={{ width: `${Math.max(0, Math.min(100, item.progress * 100))}%` }} />
            </div>
            {item.error ? <p className="upload-item__error">{item.error}</p> : null}
          </article>
        ))}
      </div>

      <div className="asset-grid">
        {assets.map(asset => (
          <button
            key={asset.id}
            type="button"
            className={`asset-card ${selectedAssetId === asset.id ? 'active' : ''}`}
            onClick={() => onSelectAsset(asset.id)}
          >
            <div className="asset-thumbnail">{asset.thumbnail}</div>
            <div className="asset-info">
              <p className="asset-title">{asset.name}</p>
              <p className="asset-meta">
                {asset.type.toUpperCase()} · {asset.durationSec}s
              </p>
            </div>
          </button>
        ))}
      </div>
    </section>
  )
}
