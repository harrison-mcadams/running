import { useCallback, useEffect, useRef, useState, type ReactElement } from 'react'
import { api, type Run, type SyncStatus } from './api'
import { IconLogo, IconModel, IconRoutes, IconRuns, IconSettings, IconSync } from './components/Icons'
import { SettingsSheet } from './components/Settings'
import { RunDetailSheet } from './components/RunDetail'
import { RunsPage } from './pages/RunsPage'
import { RoutesPage } from './pages/RoutesPage'
import { ModelPage } from './pages/ModelPage'

type Tab = 'runs' | 'routes' | 'model'

const TABS: { id: Tab; label: string; icon: () => ReactElement }[] = [
  { id: 'runs', label: 'Runs', icon: IconRuns },
  { id: 'routes', label: 'Routes', icon: IconRoutes },
  { id: 'model', label: 'Pace model', icon: IconModel },
]

function tabFromHash(): Tab {
  const h = window.location.hash.replace('#/', '').split('/')[0]
  return (TABS.find((t) => t.id === h)?.id ?? 'runs') as Tab
}

export default function App() {
  const [tab, setTab] = useState<Tab>(tabFromHash)
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sync, setSync] = useState<SyncStatus | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [dataVersion, setDataVersion] = useState(0)
  const wasRunning = useRef(false)

  const loadRuns = useCallback(() => {
    api.runs()
      .then((r) => {
        setRuns(r)
        setError(null)
      })
      .catch((e) => setError(String(e)))
  }, [])

  const dataChanged = useCallback(() => {
    loadRuns()
    setDataVersion((v) => v + 1)
  }, [loadRuns])

  useEffect(() => {
    loadRuns()
    api.syncStatus().then(setSync).catch(() => null)
    const onHash = () => {
      setTab(tabFromHash())
      setShowSettings(false)
      setDetailId(null)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [loadRuns])

  // Poll sync status while a sync runs; reload data when it finishes.
  useEffect(() => {
    if (!sync?.running) return
    const t = setInterval(() => api.syncStatus().then(setSync).catch(() => null), 1500)
    return () => clearInterval(t)
  }, [sync?.running])

  useEffect(() => {
    if (sync?.running) wasRunning.current = true
    else if (wasRunning.current) {
      wasRunning.current = false
      dataChanged()
    }
  }, [sync?.running, dataChanged])

  const startSync = (full: boolean) => {
    api.sync(full)
      .then((s) => setSync(s))
      .catch((e) => setError(String(e)))
  }

  const go = (t: Tab) => {
    window.location.hash = `#/${t}`
    setTab(t)
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <IconLogo />
          Strides
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={`tab${tab === t.id ? ' active' : ''}`} onClick={() => go(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
        <div className="spacer" />
        <button className="btn small" onClick={() => startSync(false)} disabled={sync?.running} title={sync?.running ? sync.message : 'Fetch new runs from Google'}>
          <IconSync spinning={!!sync?.running} />
          <span className="sync-label">{sync?.running ? 'Syncing' : 'Sync'}</span>
        </button>
        <button className="btn small ghost" onClick={() => setShowSettings(true)} aria-label="Settings">
          <IconSettings />
        </button>
      </header>

      <main>
        {error && (
          <div className="banner error">
            {error} <button className="btn small" onClick={loadRuns}>Retry</button>
          </div>
        )}
        {sync?.running && <div className="banner">Syncing: {sync.message}</div>}
        {!sync?.running && sync?.error && <div className="banner error">Last sync failed: {sync.error}</div>}
        {tab === 'runs' && <RunsPage runs={runs} onOpen={setDetailId} />}
        {tab === 'routes' && <RoutesPage runs={runs} onOpen={setDetailId} version={dataVersion} />}
        {tab === 'model' && <ModelPage version={dataVersion} />}
      </main>

      <nav className="bottomnav">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? 'active' : ''} onClick={() => go(t.id)}>
            <t.icon />
            {t.label}
          </button>
        ))}
      </nav>

      {detailId && <RunDetailSheet id={detailId} onClose={() => setDetailId(null)} onChanged={dataChanged} />}
      {showSettings && <SettingsSheet onClose={() => setShowSettings(false)} sync={sync} onSync={startSync} onDataChanged={dataChanged} />}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } } @media (max-width: 480px) { .sync-label { display: none } }`}</style>
    </div>
  )
}
