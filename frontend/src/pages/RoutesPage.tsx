import { useEffect, useMemo, useState } from 'react'
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { api, type Group, type GroupDetail, type GroupMember, type Run } from '../api'
import { dayNumberToIso, fmtDate, fmtNum, fmtPace, fmtSigned, linearTrend, toDayNumber } from '../lib/format'
import { axisProps, clickedRunId, gridProps, Legend, paceDomain, paceTicks, series, Tip, type RechartsTip } from '../components/charts'
import { RouteMap } from '../components/RouteMap'

export function RoutesPage({ runs, onOpen, version }: { runs: Run[] | null; onOpen: (id: string) => void; version: number }) {
  const [groups, setGroups] = useState<Group[] | null>(null)
  const [groupId, setGroupId] = useState<number | null>(null)
  const [focus, setFocus] = useState<string | undefined>(undefined)
  const [detail, setDetail] = useState<GroupDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [headings, setHeadings] = useState<Set<string> | null>(null)
  const [distTol, setDistTol] = useState(1.0)
  const [minOverlap, setMinOverlap] = useState(0)
  const [renaming, setRenaming] = useState(false)
  const [nameDraft, setNameDraft] = useState('')

  useEffect(() => {
    api.groups().then((g) => {
      setGroups(g)
      setGroupId((cur) => cur ?? g[0]?.group_id ?? null)
    })
  }, [version])

  useEffect(() => {
    if (groupId == null) return
    setLoading(true)
    api.group(groupId, focus)
      .then((d) => {
        setDetail(d)
        setHeadings(null)
      })
      .finally(() => setLoading(false))
  }, [groupId, focus, version])

  const focusRun = detail?.members.find((m) => m.id === detail.focus_id) ?? null

  const included = useMemo(() => {
    if (!detail || !focusRun) return []
    return detail.members.filter((m) => {
      if (m.id === focusRun.id) return true
      if (headings && m.heading && !headings.has(m.heading)) return false
      if (Math.abs(m.distance_mi - focusRun.distance_mi) > distTol) return false
      if (m.overlap < minOverlap / 100) return false
      return true
    })
  }, [detail, focusRun, headings, distTol, minOverlap])

  const others = included.filter((m) => m.id !== focusRun?.id)
  const avgPace = others.length ? others.reduce((a, m) => a + (m.pace_sec_mi ?? 0), 0) / others.length : null
  const hrOthers = others.filter((m) => m.avg_hr)
  const avgHr = hrOthers.length ? hrOthers.reduce((a, m) => a + (m.avg_hr ?? 0), 0) / hrOthers.length : null
  const bestOther = others.length ? Math.min(...others.map((m) => m.pace_sec_mi ?? 1e9)) : null

  if (!runs) return <div className="empty">Loading…</div>
  if (!groups) return <div className="empty">Finding your routes…</div>
  if (!groups.length) return <div className="empty">No GPS routes yet. Sync to download routes, then come back.</div>

  const allHeadings = detail ? [...new Set(detail.members.map((m) => m.heading).filter(Boolean) as string[])] : []
  const group = detail?.group

  const saveName = async () => {
    if (!group) return
    await api.renameGroup(group.group_id, nameDraft)
    setRenaming(false)
    const g = await api.groups()
    setGroups(g)
    setDetail((d) => (d ? { ...d, group: g.find((x) => x.group_id === group.group_id) ?? d.group } : d))
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Routes</h1>
          <p>Runs grouped by the trail they follow. Pick a route, then a run to compare against the others.</p>
        </div>
      </div>

      <div className="group-cards">
        {groups.map((g) => (
          <button key={g.group_id} className={`group-card${g.group_id === groupId ? ' active' : ''}`} onClick={() => { setGroupId(g.group_id); setFocus(undefined) }}>
            <div className="name">{g.name}</div>
            <div className="meta">
              {g.n_runs} run{g.n_runs === 1 ? '' : 's'} · {g.distance_range_mi[0] === g.distance_range_mi[1] ? `${fmtNum(g.median_distance_mi, 1)} mi` : `${fmtNum(g.distance_range_mi[0], 1)}–${fmtNum(g.distance_range_mi[1], 1)} mi`} · last {fmtDate(g.last_date)}
            </div>
          </button>
        ))}
      </div>

      {detail && focusRun && group && (
        <div className={loading ? 'loading' : ''} style={{ marginTop: 14 }}>
          <div className="card">
            <div className="card-head">
              {renaming ? (
                <div className="field row">
                  <input type="text" value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} placeholder={group.auto_name} autoFocus onKeyDown={(e) => e.key === 'Enter' && saveName()} />
                  <button className="btn small primary" onClick={saveName}>Save</button>
                  <button className="btn small ghost" onClick={() => setRenaming(false)}>Cancel</button>
                </div>
              ) : (
                <h2>
                  {group.name}{' '}
                  <button className="btn small ghost" onClick={() => { setNameDraft(group.custom_name ?? ''); setRenaming(true) }}>
                    rename
                  </button>
                </h2>
              )}
              <p>{group.n_runs} runs · {detail.members.filter((m) => m.has_hr).length} with heart rate</p>
            </div>

            <div className="filters" style={{ marginBottom: 12 }}>
              <label className="field" style={{ minWidth: 220, flex: 1 }}>
                <span>Compare this run</span>
                <select value={focusRun.id} onChange={(e) => setFocus(e.target.value)}>
                  {[...detail.members].reverse().map((m) => (
                    <option key={m.id} value={m.id}>
                      {fmtDate(m.date, { month: 'short', day: 'numeric', year: 'numeric' })} · {fmtNum(m.distance_mi, 1)} mi · {m.pace_str}/mi{m.heading ? ` · ${m.heading}` : ''}
                    </option>
                  ))}
                </select>
              </label>
              {allHeadings.length > 1 && (
                <div className="field">
                  <span>Direction out</span>
                  <div className="seg">
                    <button className={!headings ? 'active' : ''} onClick={() => setHeadings(null)}>Any</button>
                    {allHeadings.map((h) => (
                      <button key={h} className={headings?.has(h) && headings.size === 1 ? 'active' : ''} onClick={() => setHeadings(new Set([h]))}>{h}</button>
                    ))}
                  </div>
                </div>
              )}
              <div className="field" style={{ minWidth: 150 }}>
                <div className="slider">
                  <span>Distance within</span>
                  <span className="val">±{fmtNum(distTol, 1)} mi</span>
                  <input type="range" min="0.1" max="3" step="0.1" value={distTol} onChange={(e) => setDistTol(Number(e.target.value))} />
                </div>
              </div>
              <div className="field" style={{ minWidth: 150 }}>
                <div className="slider">
                  <span>Route overlap at least</span>
                  <span className="val">{minOverlap}%</span>
                  <input type="range" min="0" max="100" step="5" value={minOverlap} onChange={(e) => setMinOverlap(Number(e.target.value))} />
                </div>
              </div>
            </div>

            <div className="tiles">
              <Tile label="This run" value={`${focusRun.pace_str} /mi`} sub={`${fmtDate(focusRun.date)} · ${fmtNum(focusRun.distance_mi, 2)} mi${focusRun.avg_hr ? ` · ${focusRun.avg_hr} bpm` : ''}`} />
              <Tile label={`Average of ${others.length} similar`} value={avgPace ? `${fmtPace(avgPace)} /mi` : '–'} sub={avgHr ? `${Math.round(avgHr)} bpm average` : undefined} />
              <Tile
                label="Versus average"
                value={avgPace && focusRun.pace_sec_mi ? `${fmtSigned(focusRun.pace_sec_mi - avgPace)} s/mi` : '–'}
                sub={avgPace && focusRun.pace_sec_mi ? (focusRun.pace_sec_mi < avgPace ? 'faster than usual' : 'slower than usual') : 'no comparable runs'}
                tone={avgPace && focusRun.pace_sec_mi ? (focusRun.pace_sec_mi < avgPace ? 'good' : 'bad') : undefined}
              />
              <Tile label="Best similar run" value={bestOther ? `${fmtPace(bestOther)} /mi` : '–'} sub={bestOther && focusRun.pace_sec_mi ? `${fmtSigned(focusRun.pace_sec_mi - bestOther)} s/mi vs this run` : undefined} />
            </div>
          </div>

          <div className="grid-2" style={{ marginTop: 14 }}>
            <div className="card">
              <div className="card-head">
                <h2>Where</h2>
                <p>Selected run over the route's reference track</p>
              </div>
              <RouteMap lines={[{ points: detail.reference_route, color: 'var(--ink-3)', weight: 6, opacity: 0.35 }, { points: detail.focus_route, color: 'var(--series-1)', weight: 3 }]} />
              <Legend items={[{ color: 'var(--series-1)', label: 'Selected run' }, { color: 'var(--ink-3)', label: 'Reference track' }]} />
            </div>

            <div className="card">
              <div className="card-head">
                <h2>Pace on this route over time</h2>
                <p>Similar runs only; faster is up</p>
              </div>
              <GroupTime included={included} focusId={focusRun.id} onOpen={onOpen} />
            </div>
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <div className="card-head">
              <h2>Mile by mile</h2>
              <p>Selected run against the average of similar runs; faster is up</p>
            </div>
            <SplitsCompare focus={focusRun} others={others} />
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <div className="card-head">
              <h2>Runs on this route</h2>
              <p>Tap a row to compare against it · {included.length} of {detail.members.length} pass the filters</p>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th className="num">Miles</th>
                    <th className="num">Pace</th>
                    <th className="num">vs selected</th>
                    <th className="num">HR</th>
                    <th>Out</th>
                    <th className="num">Overlap</th>
                    <th>Weather</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {[...detail.members].reverse().map((m) => {
                    const inc = included.some((x) => x.id === m.id)
                    const d = m.pace_sec_mi && focusRun.pace_sec_mi ? m.pace_sec_mi - focusRun.pace_sec_mi : null
                    return (
                      <tr key={m.id} className={`clickable${m.id === focusRun.id ? ' focus' : ''}`} style={inc ? undefined : { opacity: 0.45 }} onClick={() => setFocus(m.id)}>
                        <td>{fmtDate(m.date, { weekday: 'short', month: 'short', day: 'numeric', year: '2-digit' })}</td>
                        <td className="num">{fmtNum(m.distance_mi, 2)}</td>
                        <td className="num">{m.pace_str}</td>
                        <td className={`num ${d == null || m.id === focusRun.id ? 'muted' : d < 0 ? 'delta-good' : 'delta-bad'}`}>{m.id === focusRun.id ? 'selected' : d == null ? '–' : `${fmtSigned(d)} s`}</td>
                        <td className="num">{m.avg_hr ?? '–'}</td>
                        <td>{m.heading ?? '–'}</td>
                        <td className="num">{Math.round(m.overlap * 100)}%</td>
                        <td className="muted small">{m.weather ? `${m.weather.temp_f}°F · ${m.weather.humidity}%` : '–'}</td>
                        <td>
                          <button className="btn small ghost" onClick={(e) => { e.stopPropagation(); onOpen(m.id) }}>
                            details
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className={`value${tone === 'good' ? ' delta-good' : tone === 'bad' ? ' delta-bad' : ''}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

interface Pt {
  x: number
  y: number
  run: GroupMember
}

function GroupTime({ included, focusId, onOpen }: { included: GroupMember[]; focusId: string; onOpen: (id: string) => void }) {
  const pts: Pt[] = included.filter((m) => m.pace_sec_mi).map((m) => ({ x: toDayNumber(m.date), y: m.pace_sec_mi as number, run: m }))
  if (pts.length < 1) return <div className="empty">Nothing to plot.</div>
  const domain = paceDomain(pts.map((p) => p.y))
  const trend = linearTrend(pts.map((p) => p.x), pts.map((p) => p.y))
  const xs = pts.map((p) => p.x)
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
  const trendData = trend && pts.length > 2 ? [{ x: x0, y: trend.intercept + trend.slope * x0 }, { x: x1, y: trend.intercept + trend.slope * x1 }] : []
  const othersPts = pts.filter((p) => p.run.id !== focusId)
  const focusPts = pts.filter((p) => p.run.id === focusId)
  return (
    <>
      <div className="chart">
        <ResponsiveContainer>
          <ScatterChart margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="x" type="number" domain={[x0 - 5, x1 + 5]} tickFormatter={(v) => fmtDate(dayNumberToIso(v))} {...axisProps} />
            <YAxis dataKey="y" type="number" domain={domain} ticks={paceTicks(domain)} reversed tickFormatter={fmtPace} width={44} {...axisProps} />
            <ZAxis range={[60, 60]} />
            <Tooltip cursor={false} content={(p: RechartsTip) => tip(p)} />
            {trendData.length === 2 && <ReferenceLine segment={[trendData[0], trendData[1]]} stroke="var(--ink-3)" strokeWidth={1.5} ifOverflow="hidden" />}
            <Scatter data={othersPts} fill={series.blue} stroke="var(--surface)" strokeWidth={2} isAnimationActive={false} onClick={(d) => { const id = clickedRunId(d); if (id) onOpen(id) }} />
            <Scatter data={focusPts} fill={series.orange} stroke="var(--surface)" strokeWidth={2} shape={(p: { cx?: number; cy?: number }) => <circle cx={p.cx} cy={p.cy} r={8} fill={series.orange} stroke="var(--surface)" strokeWidth={2} />} isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <Legend items={[{ color: series.orange, label: 'Selected run', dot: true }, { color: series.blue, label: 'Similar runs', dot: true }, { color: 'var(--ink-3)', label: 'Trend' }]} />
    </>
  )
}

function tip(p: RechartsTip) {
  if (!p.active || !p.payload?.length) return null
  const r = (p.payload[0].payload as Pt).run
  if (!r) return null
  return <Tip title={`${fmtDate(r.date, { weekday: 'short', month: 'short', day: 'numeric' })} · ${r.time}`} rows={[{ label: 'Pace', value: `${r.pace_str} /mi` }, { label: 'Distance', value: `${fmtNum(r.distance_mi, 2)} mi` }, { label: 'Heart rate', value: r.avg_hr ? `${r.avg_hr} bpm` : '–' }, { label: 'Overlap', value: `${Math.round(r.overlap * 100)}%` }]} />
}

function SplitsCompare({ focus, others }: { focus: GroupMember; others: GroupMember[] }) {
  if (!focus.splits.length) return <div className="empty">No splits for the selected run.</div>
  const rows = focus.splits.map((s) => {
    const peers = others.map((o) => o.splits.find((x) => x.index === s.index)?.pace_sec_mi).filter((v): v is number => v != null && v > 0)
    const avg = peers.length ? peers.reduce((a, b) => a + b, 0) / peers.length : null
    const best = peers.length ? Math.min(...peers) : null
    return { mile: s.index, focus: s.pace_sec_mi, avg, best, n: peers.length, partial: s.distance_mi < 0.95 }
  })
  const all = rows.flatMap((r) => [r.focus ?? 0, r.avg ?? 0, r.best ?? 0]).filter((v) => v > 0)
  const domain = paceDomain(all)
  return (
    <>
      <div className="chart short">
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="mile" type="number" domain={[1, rows.length]} ticks={rows.map((r) => r.mile)} tickFormatter={(v) => `mi ${v}`} {...axisProps} />
            <YAxis domain={domain} ticks={paceTicks(domain)} reversed tickFormatter={fmtPace} width={44} {...axisProps} />
            <Tooltip
              content={(p: RechartsTip) => {
                if (!p.active || !p.payload?.length) return null
                const r = p.payload[0].payload as (typeof rows)[number]
                return <Tip title={`Mile ${r.mile}${r.partial ? ' (partial)' : ''}`} rows={[{ label: 'Selected', value: fmtPace(r.focus) }, { label: `Avg of ${r.n}`, value: fmtPace(r.avg) }, { label: 'Best', value: fmtPace(r.best) }]} />
              }}
            />
            <Line type="monotone" dataKey="best" stroke={series.aqua} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)', fill: series.aqua }} isAnimationActive={false} connectNulls />
            <Line type="monotone" dataKey="avg" stroke={series.blue} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)', fill: series.blue }} isAnimationActive={false} connectNulls />
            <Line type="monotone" dataKey="focus" stroke={series.orange} strokeWidth={2.5} dot={{ r: 5, strokeWidth: 2, stroke: 'var(--surface)', fill: series.orange }} isAnimationActive={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <Legend items={[{ color: series.orange, label: 'Selected run' }, { color: series.blue, label: 'Average of similar runs' }, { color: series.aqua, label: 'Best similar split' }]} />
    </>
  )
}
