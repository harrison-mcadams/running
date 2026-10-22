import { useMemo, useState } from 'react'
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import type { Run } from '../api'
import { dayNumberToIso, fmtDate, fmtNum, fmtPace, linearTrend, toDayNumber } from '../lib/format'
import { axisProps, clickedRunId, gridProps, Legend, paceDomain, paceTicks, series, Tip, type RechartsTip } from '../components/charts'

type SortKey = 'date' | 'distance_mi' | 'pace_sec_mi' | 'avg_hr' | 'duration_sec' | 'temp' | 'elevation_gain_ft'

const PRESETS: { id: string; label: string; days?: number }[] = [
  { id: 'all', label: 'All' },
  { id: '30', label: '30d', days: 30 },
  { id: '90', label: '90d', days: 90 },
  { id: '365', label: '1y', days: 365 },
]

export function RunsPage({ runs, onOpen }: { runs: Run[] | null; onOpen: (id: string) => void }) {
  const [preset, setPreset] = useState('all')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [minDist, setMinDist] = useState('')
  const [maxDist, setMaxDist] = useState('')
  const [group, setGroup] = useState('')
  const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({ key: 'date', asc: false })

  const groups = useMemo(() => {
    const m = new Map<number, string>()
    runs?.forEach((r) => r.group_id != null && m.set(r.group_id, r.group_name ?? `Route ${r.group_id}`))
    return [...m.entries()].sort((a, b) => a[0] - b[0])
  }, [runs])

  const filtered = useMemo(() => {
    if (!runs) return []
    const lastDate = runs.length ? runs[runs.length - 1].date : ''
    let lo = start
    if (preset !== 'all') {
      const days = PRESETS.find((p) => p.id === preset)?.days ?? 0
      lo = dayNumberToIso(toDayNumber(lastDate) - days)
    }
    return runs.filter((r) => {
      if (lo && r.date < lo) return false
      if (preset === 'all' && end && r.date > end) return false
      if (minDist && r.distance_mi < Number(minDist)) return false
      if (maxDist && r.distance_mi > Number(maxDist)) return false
      if (group && String(r.group_id) !== group) return false
      return true
    })
  }, [runs, preset, start, end, minDist, maxDist, group])

  const sorted = useMemo(() => {
    const val = (r: Run): number | string => {
      switch (sort.key) {
        case 'temp':
          return r.weather?.temp_f ?? -999
        case 'date':
          return r.local_datetime
        default:
          return (r[sort.key] as number | null) ?? -999
      }
    }
    return [...filtered].sort((a, b) => {
      const va = val(a)
      const vb = val(b)
      const c = va < vb ? -1 : va > vb ? 1 : 0
      return sort.asc ? c : -c
    })
  }, [filtered, sort])

  const totals = useMemo(() => {
    const miles = filtered.reduce((a, r) => a + r.distance_mi, 0)
    const secs = filtered.reduce((a, r) => a + (r.duration_sec ?? 0), 0)
    const hrRuns = filtered.filter((r) => r.avg_hr)
    const hr = hrRuns.length ? hrRuns.reduce((a, r) => a + (r.avg_hr ?? 0), 0) / hrRuns.length : null
    return { n: filtered.length, miles, pace: miles ? secs / miles : null, hr }
  }, [filtered])

  if (!runs) return <div className="empty">Loading runs…</div>
  if (!runs.length)
    return (
      <div className="empty">
        No runs yet. Open Settings, connect Google, and sync.
      </div>
    )

  const toggleSort = (key: SortKey) => setSort((s) => (s.key === key ? { key, asc: !s.asc } : { key, asc: key === 'date' ? false : true }))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Runs</h1>
          <p>
            {runs.length} runs on record, {fmtDate(runs[0].date, { month: 'short', year: 'numeric' })} to {fmtDate(runs[runs.length - 1].date, { month: 'short', year: 'numeric' })}
          </p>
        </div>
      </div>

      <div className="filters">
        <div className="field">
          <span>Period</span>
          <div className="seg">
            {PRESETS.map((p) => (
              <button key={p.id} className={preset === p.id ? 'active' : ''} onClick={() => setPreset(p.id)}>
                {p.label}
              </button>
            ))}
          </div>
        </div>
        {preset === 'all' && (
          <>
            <label className="field">
              <span>From</span>
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label className="field">
              <span>To</span>
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </label>
          </>
        )}
        <div className="field">
          <span>Distance (mi)</span>
          <div className="field row">
            <input type="number" step="0.5" min="0" placeholder="min" value={minDist} onChange={(e) => setMinDist(e.target.value)} style={{ width: 72 }} />
            <span className="muted">–</span>
            <input type="number" step="0.5" min="0" placeholder="max" value={maxDist} onChange={(e) => setMaxDist(e.target.value)} style={{ width: 72 }} />
          </div>
        </div>
        {groups.length > 0 && (
          <label className="field">
            <span>Route</span>
            <select value={group} onChange={(e) => setGroup(e.target.value)}>
              <option value="">Any route</option>
              {groups.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
        {(preset !== 'all' || start || end || minDist || maxDist || group) && (
          <button
            className="btn small ghost"
            onClick={() => {
              setPreset('all')
              setStart('')
              setEnd('')
              setMinDist('')
              setMaxDist('')
              setGroup('')
            }}
          >
            Reset
          </button>
        )}
      </div>

      <div className="tiles">
        <Tile label="Runs" value={`${totals.n}`} />
        <Tile label="Miles" value={fmtNum(totals.miles, 1)} />
        <Tile label="Average pace" value={fmtPace(totals.pace)} sub="per mile, time-weighted" />
        <Tile label="Average heart rate" value={totals.hr ? `${Math.round(totals.hr)}` : '–'} sub="bpm" />
      </div>

      <div className="grid-2" style={{ marginTop: 14 }}>
        <div className="card">
          <div className="card-head">
            <h2>Pace over time</h2>
            <p>Faster is up</p>
          </div>
          <TimeChart runs={filtered} metric="pace_sec_mi" color={series.blue} reversed fmt={fmtPace} onOpen={onOpen} unit="/mi" />
        </div>
        <div className="card">
          <div className="card-head">
            <h2>Heart rate over time</h2>
            <p>Average bpm per run</p>
          </div>
          <TimeChart runs={filtered.filter((r) => r.avg_hr)} metric="avg_hr" color={series.red} fmt={(v) => `${Math.round(v)}`} onOpen={onOpen} unit="bpm" />
        </div>
        <div className="card">
          <div className="card-head">
            <h2>Distance over time</h2>
            <p>Miles per run</p>
          </div>
          <TimeChart runs={filtered} metric="distance_mi" color={series.aqua} fmt={(v) => fmtNum(v, 1)} onOpen={onOpen} unit="mi" domainZero />
        </div>
        <div className="card">
          <div className="card-head">
            <h2>Pace by distance</h2>
            <p>Each dot is a run; faster is up</p>
          </div>
          <DistancePace runs={filtered} onOpen={onOpen} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-head">
          <h2>All runs</h2>
          <p>{filtered.length} shown · tap a row for the map, splits and heart rate</p>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <Th k="date" sort={sort} onClick={toggleSort} label="Date" />
                <Th k="distance_mi" sort={sort} onClick={toggleSort} label="Miles" num />
                <Th k="duration_sec" sort={sort} onClick={toggleSort} label="Time" num />
                <Th k="pace_sec_mi" sort={sort} onClick={toggleSort} label="Pace" num />
                <Th k="avg_hr" sort={sort} onClick={toggleSort} label="HR" num />
                <Th k="elevation_gain_ft" sort={sort} onClick={toggleSort} label="Gain" num />
                <Th k="temp" sort={sort} onClick={toggleSort} label="Weather" />
                <th>Route</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => onOpen(r.id)}>
                  <td>
                    {fmtDate(r.date, { weekday: 'short', month: 'short', day: 'numeric', year: '2-digit' })} <span className="muted small">{r.time}</span>
                    {r.n_comments > 0 && <span className="tag" title={`${r.n_comments} note${r.n_comments === 1 ? '' : 's'}`}>✎ {r.n_comments}</span>}
                    {r.excluded_from_model && <span className="tag" title="Left out of the pace model">not in model</span>}
                  </td>
                  <td className="num">{fmtNum(r.distance_mi, 2)}</td>
                  <td className="num">{r.duration_str ?? '–'}</td>
                  <td className="num">{r.pace_str ?? '–'}</td>
                  <td className="num">{r.avg_hr ?? '–'}</td>
                  <td className="num">{r.elevation_gain_ft != null ? `${r.elevation_gain_ft} ft` : '–'}</td>
                  <td>{r.weather ? `${r.weather.temp_f}°F · ${r.weather.humidity}% · ${r.weather.condition}` : '–'}</td>
                  <td className="muted">{r.group_name ?? (r.group_id ? `Route ${r.group_id}` : '–')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

function Th({ k, sort, onClick, label, num }: { k: SortKey; sort: { key: SortKey; asc: boolean }; onClick: (k: SortKey) => void; label: string; num?: boolean }) {
  const active = sort.key === k
  return (
    <th className={`${num ? 'num ' : ''}${active ? 'sorted' : ''}`} onClick={() => onClick(k)}>
      {label}
      {active ? (sort.asc ? ' ↑' : ' ↓') : ''}
    </th>
  )
}

interface Pt {
  x: number
  y: number
  run: Run
}

function TimeChart({ runs, metric, color, reversed, fmt, onOpen, unit, domainZero }: { runs: Run[]; metric: 'pace_sec_mi' | 'avg_hr' | 'distance_mi'; color: string; reversed?: boolean; fmt: (v: number) => string; onOpen: (id: string) => void; unit: string; domainZero?: boolean }) {
  const pts: Pt[] = runs.filter((r) => r[metric] != null).map((r) => ({ x: toDayNumber(r.date) + hourFrac(r.time), y: r[metric] as number, run: r }))
  if (!pts.length) return <div className="empty">No runs match.</div>
  const trend = linearTrend(pts.map((p) => p.x), pts.map((p) => p.y))
  const xs = pts.map((p) => p.x)
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
  const trendData = trend ? [{ x: x0, y: trend.intercept + trend.slope * x0 }, { x: x1, y: trend.intercept + trend.slope * x1 }] : []
  const ys = pts.map((p) => p.y)
  const domain: [number, number] = metric === 'pace_sec_mi' ? paceDomain(ys) : domainZero ? [0, Math.ceil(Math.max(...ys) + 1)] : [Math.floor(Math.min(...ys) - 5), Math.ceil(Math.max(...ys) + 5)]
  const perMonth = trend ? trend.slope * 30.4 : 0
  return (
    <>
      <div className="chart">
        <ResponsiveContainer>
          <ScatterChart margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="x" type="number" domain={[x0 - 3, x1 + 3]} tickFormatter={(v) => fmtDate(dayNumberToIso(v))} {...axisProps} />
            <YAxis dataKey="y" type="number" domain={domain} ticks={metric === 'pace_sec_mi' ? paceTicks(domain) : undefined} reversed={reversed} tickFormatter={fmt} width={44} {...axisProps} />
            <ZAxis range={[60, 60]} />
            <Tooltip cursor={false} content={(p: RechartsTip) => runTip(p, metric, fmt, unit)} />
            {trendData.length === 2 && <ReferenceLine segment={[trendData[0], trendData[1]]} stroke="var(--ink-3)" strokeWidth={1.5} ifOverflow="hidden" />}
            <Scatter data={pts} fill={color} stroke="var(--surface)" strokeWidth={2} isAnimationActive={false} onClick={(d) => { const id = clickedRunId(d); if (id) onOpen(id) }} style={{ cursor: 'pointer' }} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      {trend && pts.length > 3 && (
        <p className="note" style={{ marginTop: 2 }}>
          Trend: {perMonth > 0 ? '+' : ''}
          {metric === 'pace_sec_mi' ? `${perMonth.toFixed(1)} s/mi` : `${perMonth.toFixed(1)} ${unit}`} per month
          {metric === 'pace_sec_mi' ? (perMonth < 0 ? ' (getting faster)' : ' (getting slower)') : ''}
        </p>
      )}
    </>
  )
}

function DistancePace({ runs, onOpen }: { runs: Run[]; onOpen: (id: string) => void }) {
  const pts: Pt[] = runs.filter((r) => r.pace_sec_mi).map((r) => ({ x: r.distance_mi, y: r.pace_sec_mi as number, run: r }))
  if (!pts.length) return <div className="empty">No runs match.</div>
  const domain = paceDomain(pts.map((p) => p.y))
  return (
    <div className="chart">
      <ResponsiveContainer>
        <ScatterChart margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="x" type="number" domain={['auto', 'auto']} tickFormatter={(v) => `${v} mi`} {...axisProps} />
          <YAxis dataKey="y" type="number" domain={domain} ticks={paceTicks(domain)} reversed tickFormatter={fmtPace} width={44} {...axisProps} />
          <ZAxis range={[60, 60]} />
          <Tooltip cursor={false} content={(p: RechartsTip) => runTip(p, 'pace_sec_mi', fmtPace, '/mi')} />
          <Scatter data={pts} fill={series.blue} stroke="var(--surface)" strokeWidth={2} isAnimationActive={false} onClick={(d) => { const id = clickedRunId(d); if (id) onOpen(id) }} style={{ cursor: 'pointer' }} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

function hourFrac(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return (h + m / 60) / 24
}

function runTip(p: RechartsTip, metric: string, fmt: (v: number) => string, unit: string) {
  if (!p.active || !p.payload?.length) return null
  const d = p.payload[0].payload as Pt
  if (!d.run) return null
  const r = d.run
  const rows = [
    { label: 'Distance', value: `${fmtNum(r.distance_mi, 2)} mi` },
    { label: 'Pace', value: `${r.pace_str ?? '–'} /mi` },
    { label: 'Heart rate', value: r.avg_hr ? `${r.avg_hr} bpm` : '–' },
  ]
  if (r.weather) rows.push({ label: 'Weather', value: `${r.weather.temp_f}°F, ${r.weather.humidity}%` })
  void metric
  void fmt
  void unit
  return <Tip title={`${fmtDate(r.date, { weekday: 'short', month: 'short', day: 'numeric' })} · ${r.time}`} rows={rows} />
}

export { Legend }
