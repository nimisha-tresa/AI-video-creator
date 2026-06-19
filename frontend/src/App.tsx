import { useEffect, useState } from 'react'

import { ModelStudio, generationToJob } from '@/components/Studio/ModelStudio'
import type { GenerationJob } from '@/types/editor'
import {
  fetchMe,
  getStoredAccessToken,
  listGenerations,
  login,
  register,
  setStoredAccessToken,
  type UserProfile,
} from '@/services/api'

import './App.css'

const DEV_AUTH = {
  email: 'demo@local.app',
  username: 'demo',
  password: 'password123',
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
  return `${Math.round(diffHr / 24)}d ago`
}

export default function App() {
  const [jobs, setJobs] = useState<GenerationJob[]>([])
  const [authStatus, setAuthStatus] = useState<'booting' | 'ready'>('booting')
  const [user, setUser] = useState<UserProfile | null>(null)
  const [accessToken, setAccessTokenState] = useState<string | null>(getStoredAccessToken())
  const [authError, setAuthError] = useState<string | null>(null)
  const [pollingPaused, setPollingPaused] = useState(false)

  async function ensureSession(): Promise<string | null> {
    try {
      let token = accessToken
      if (token) {
        try {
          setUser(await fetchMe(token))
          return token
        } catch {
          token = null
          setStoredAccessToken(null)
          setAccessTokenState(null)
        }
      }

      try {
        setUser(await fetchMe())
        return token
      } catch {
        // continue
      }

      try {
        const tokens = await login(DEV_AUTH.email, DEV_AUTH.password)
        token = tokens.access_token
      } catch {
        await register(DEV_AUTH.email, DEV_AUTH.username, DEV_AUTH.password)
        token = (await login(DEV_AUTH.email, DEV_AUTH.password)).access_token
      }

      if (!token) return null
      setStoredAccessToken(token)
      setAccessTokenState(token)
      setUser(await fetchMe(token))
      return token
    } catch {
      setAuthError('Backend unavailable — start Docker services.')
      return null
    }
  }

  async function refreshJobs(token: string | null) {
    const generations = await listGenerations(token)
    setJobs(
      generations.map(g => ({
        ...generationToJob(g),
        createdAt: formatRelativeTime(g.created_at),
        createdAtIso: g.created_at,
      })),
    )
  }

  useEffect(() => {
    let mounted = true
    void (async () => {
      setAuthStatus('booting')
      try {
        const token = await ensureSession()
        if (mounted) await refreshJobs(token)
      } finally {
        if (mounted) setAuthStatus('ready')
      }
    })()
    return () => {
      mounted = false
    }
  }, [accessToken])

  useEffect(() => {
    if (authStatus !== 'ready' || pollingPaused) return
    const interval = window.setInterval(() => void refreshJobs(accessToken), 2500)
    return () => window.clearInterval(interval)
  }, [accessToken, authStatus, pollingPaused])

  return (
    <div className="app-shell app-shell--studio">
      <header className="studio-topbar">
        <div>
          <p className="eyebrow">AI Video Creator</p>
          <h1>Studio</h1>
        </div>
        <div className="topbar-controls">
          <a className="topbar-link" href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
            API Docs
          </a>
          <span className={`chip ${authStatus === 'ready' ? 'chip--live' : ''}`}>
            {authStatus === 'ready' ? 'Connected' : 'Connecting…'}
          </span>
        </div>
      </header>

      {authError ? <div className="inline-banner inline-banner--error">{authError}</div> : null}

      <ModelStudio
        jobs={jobs}
        accessToken={accessToken}
        onJobsRefresh={() => refreshJobs(accessToken)}
        onClearJobs={() => setJobs([])}
        onGeneratingChange={setPollingPaused}
        isReady={authStatus === 'ready'}
      />
    </div>
  )
}
