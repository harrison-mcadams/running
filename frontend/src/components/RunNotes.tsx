import { useState } from 'react'
import { api, type RunComment } from '../api'

/** Comment thread for one run, plus the "use in pace model" switch. */
export function RunNotes({
  runId,
  comments,
  excluded,
  hidden,
  onChanged,
}: {
  runId: string
  comments: RunComment[]
  excluded: boolean
  hidden: boolean
  onChanged: (patch: { comments?: RunComment[]; excluded_from_model?: boolean; hidden?: boolean }) => void
}) {
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const act = async (fn: () => Promise<void>) => {
    setBusy(true)
    setErr(null)
    try {
      await fn()
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  const add = () =>
    act(async () => {
      const c = await api.addComment(runId, draft.trim())
      onChanged({ comments: [...comments, c] })
      setDraft('')
    })

  const remove = (id: number) =>
    act(async () => {
      if (!window.confirm('Delete this comment?')) return
      await api.deleteComment(runId, id)
      onChanged({ comments: comments.filter((c) => c.id !== id) })
    })

  const toggle = () =>
    act(async () => {
      const r = await api.setExcluded(runId, !excluded)
      onChanged({ excluded_from_model: r.excluded_from_model })
    })

  const toggleHidden = () =>
    act(async () => {
      if (!hidden && !window.confirm('Hide this run everywhere? You can bring it back from Settings → Hidden runs.')) return
      const r = await api.setHidden(runId, !hidden)
      onChanged({ hidden: r.hidden })
    })

  return (
    <div className="card notes">
      <div className="card-head">
        <h2>Notes</h2>
        <label className="switch" title="Excluded runs still appear everywhere else; they just don't train the pace model.">
          <input type="checkbox" checked={!excluded} onChange={toggle} disabled={busy} />
          <span>Use in pace model</span>
        </label>
      </div>
      {hidden && (
        <div className="banner">
          This run is hidden from every view. <button className="link" onClick={toggleHidden} disabled={busy}>Unhide</button>
        </div>
      )}
      {excluded && !hidden && <div className="banner">This run is left out of the pace model. It still shows in your runs and routes.</div>}
      {err && <div className="banner error">{err}</div>}
      {comments.length > 0 ? (
        <ul className="comments">
          {comments.map((c) => (
            <li key={c.id}>
              <div className="comment-body">{c.body}</div>
              <div className="comment-meta">
                {new Date(c.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })}
                <button className="link" onClick={() => remove(c.id)} disabled={busy}>
                  delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small" style={{ margin: '0 0 8px' }}>
          No notes yet. How did it feel? Anything unusual: a stop, a hill repeat, a sore calf?
        </p>
      )}
      <div className="comment-form">
        <textarea
          rows={2}
          placeholder="Add a note…"
          value={draft}
          maxLength={4000}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && draft.trim()) add()
          }}
        />
        <button className="btn primary small" onClick={add} disabled={busy || !draft.trim()}>
          Add
        </button>
      </div>
      {!hidden && (
        <div style={{ marginTop: 10, textAlign: 'right' }}>
          <button className="link" onClick={toggleHidden} disabled={busy} title="Remove this run from the runs list, totals, charts, routes and the model">
            Hide this run everywhere
          </button>
        </div>
      )}
    </div>
  )
}
