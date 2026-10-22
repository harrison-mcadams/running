import { useEffect, useState } from 'react'
import { api, type AuthStatus, type Run, type Settings, type SyncStatus } from '../api'
import { fmtDate, fmtNum } from '../lib/format'

export function SettingsSheet({ onClose, sync, onSync, onDataChanged }: { onClose: () => void; sync: SyncStatus | null; onSync: (full: boolean) => void; onDataChanged: () => void }) {
  const [auth, setAuth] = useState<AuthStatus | null>(null)
  const [token, setToken] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [settings, setSettings] = useState<Settings | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refreshAuth = () => api.authStatus().then(setAuth).catch(() => setAuth(null))
  useEffect(() => {
    refreshAuth()
    api.settings().then(setSettings).catch(() => null)
    const onFocus = () => refreshAuth()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('focus', onFocus)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('focus', onFocus)
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    setMsg(null)
    try {
      await fn()
      setMsg(ok)
      refreshAuth()
    } catch (e) {
      setMsg(String(e))
    } finally {
      setBusy(false)
    }
  }

  const connected = auth?.has_client && auth?.has_refresh_token

  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="sheet-head">
          <h2 style={{ fontSize: 18 }}>Settings</h2>
          <button className="close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {msg && <div className={`banner${/fail|error|invalid/i.test(msg) ? ' error' : ''}`}>{msg}</div>}

        <div className="card">
          <div className="card-head">
            <h2>Google account</h2>
            <span className="chip" style={{ color: connected ? 'var(--good-text)' : 'var(--critical)' }}>
              {auth == null ? 'checking…' : connected ? '● Connected' : auth.has_client ? '○ Not authorized' : '○ No client credentials'}
            </span>
          </div>
          <p className="note" style={{ marginTop: 0 }}>
            Runs come from the Google Health API (your Pixel Watch via Fitbit). Connect once; the server keeps a refresh token and renews access on each sync. Reconnect here if a sync reports an authorization error.
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
            <a className="btn primary" href="/api/auth/google" target="_blank" rel="noreferrer" aria-disabled={!auth?.has_client}>
              {connected ? 'Reconnect Google' : 'Connect Google'}
            </a>
            <button className="btn" disabled={!connected || sync?.running} onClick={() => onSync(false)}>
              Sync now
            </button>
            <button className="btn ghost" disabled={!connected || sync?.running} onClick={() => onSync(true)}>
              Full re-sync
            </button>
          </div>
          <details style={{ marginTop: 12 }}>
            <summary>Paste a refresh token instead</summary>
            <div className="field" style={{ marginTop: 8 }}>
              <input type="text" className="wide" placeholder="1//…" value={token} onChange={(e) => setToken(e.target.value)} />
              <button className="btn small" disabled={!token || busy} onClick={() => run(() => api.saveToken(token).then(() => setToken('')), 'Refresh token saved.')}>
                Save token
              </button>
            </div>
          </details>
          <details style={{ marginTop: 8 }}>
            <summary>OAuth client id and secret</summary>
            <div className="form-grid" style={{ marginTop: 8 }}>
              <input type="text" placeholder="client_id" value={clientId} onChange={(e) => setClientId(e.target.value)} />
              <input type="text" placeholder="client_secret" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} />
            </div>
            <p className="note">
              From Google Cloud Console → Credentials. Add <code>{window.location.origin}/api/auth/google/callback</code> as an authorized redirect URI.
            </p>
            <button className="btn small" disabled={!clientId || !clientSecret || busy} onClick={() => run(() => api.saveClient(clientId, clientSecret), 'Client credentials saved.')}>
              Save client
            </button>
          </details>
        </div>

        <div className="card">
          <div className="card-head">
            <h2>Sync</h2>
            {sync?.last_sync && (
              <p>
                Last: {new Date(sync.last_sync.started_at).toLocaleString()} · {sync.last_sync.status} · {sync.last_sync.new_activities} new
              </p>
            )}
          </div>
          {sync?.running && <div className="banner">{sync.message || 'Working…'}</div>}
          {sync?.error && !sync.running && <div className="banner error">{sync.error}</div>}
          {sync?.log?.length ? <div className="log">{sync.log.join('\n')}</div> : <p className="muted small">No sync this session yet.</p>}
        </div>

        <HiddenRuns onDataChanged={onDataChanged} />

        {settings && (
          <div className="card">
            <div className="card-head">
              <h2>Data rules</h2>
              <p>Stored on the server; changes apply to every view.</p>
            </div>
            <div className="form-grid">
              <label className="field">
                <span>Hide runs before</span>
                <input type="date" value={settings.hidden_before} onChange={(e) => setSettings({ ...settings, hidden_before: e.target.value })} />
              </label>
              <label className="field">
                <span>Minimum distance (mi)</span>
                <input type="number" step="0.1" value={settings.min_distance_mi} onChange={(e) => setSettings({ ...settings, min_distance_mi: e.target.value })} />
              </label>
              <label className="field">
                <span>Slowest pace to count (sec/mi)</span>
                <input type="number" step="10" value={settings.max_pace_sec_mi} onChange={(e) => setSettings({ ...settings, max_pace_sec_mi: e.target.value })} />
              </label>
              <label className="field">
                <span>Route match radius (m)</span>
                <input type="number" step="5" value={settings.match_radius_m} onChange={(e) => setSettings({ ...settings, match_radius_m: e.target.value })} />
              </label>
              <label className="field">
                <span>Same-route coverage (0–1)</span>
                <input type="number" step="0.05" min="0" max="1" value={settings.group_coverage} onChange={(e) => setSettings({ ...settings, group_coverage: e.target.value })} />
              </label>
            </div>
            <div style={{ marginTop: 12 }}>
              <button
                className="btn primary"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    await api.saveSettings(settings)
                    onDataChanged()
                  }, 'Settings saved.')
                }
              >
                Save
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function HiddenRuns({ onDataChanged }: { onDataChanged: () => void }) {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  useEffect(() => {
    api.hiddenRuns().then(setRuns).catch(() => setRuns([]))
  }, [])
  const unhide = async (id: string) => {
    setBusy(id)
    try {
      await api.setHidden(id, false)
      setRuns((cur) => (cur ?? []).filter((r) => r.id !== id))
      onDataChanged()
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className="card">
      <div className="card-head">
        <h2>Hidden runs</h2>
        <p>Left out of every view. Hide a run from its detail sheet.</p>
      </div>
      {runs == null ? (
        <p className="muted small">Loading…</p>
      ) : runs.length === 0 ? (
        <p className="muted small">No hidden runs.</p>
      ) : (
        <table>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td>{fmtDate(r.date, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}</td>
                <td className="num">{fmtNum(r.distance_mi, 2)} mi</td>
                <td className="num">{r.pace_str ?? '–'} /mi</td>
                <td className="num">
                  <button className="btn small" onClick={() => unhide(r.id)} disabled={busy === r.id}>
                    Unhide
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
