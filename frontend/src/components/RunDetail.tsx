import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, LabelList } from 'recharts'
import { api, type RunDetail as RunDetailT } from '../api'
import { fmtDateLong, fmtDuration, fmtNum, fmtPace, fmtTime12 } from '../lib/format'
import { axisProps, gridProps, paceDomain, paceTicks, series, Tip, type RechartsTip } from './charts'
import { RouteMap } from './RouteMap'
import { RunNotes } from './RunNotes'

export function RunDetailSheet({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const [run, setRun] = useState<RunDetailT | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setRun(null)
    api.run(id).then(setRun).catch((e) => setErr(String(e)))
  }, [id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (e.key === 'Escape' && tag !== 'TEXTAREA' && tag !== 'INPUT') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="sheet-head">
          <div>
            <h2 style={{ fontSize: 18 }}>{run ? fmtDateLong(run.date) : 'Loading…'}</h2>
            {run && (
              <p className="muted small" style={{ margin: 0 }}>
                {fmtTime12(run.time)}
                {run.group_name ? ` · ${run.group_name}` : ''}
                {run.weather ? ` · ${run.weather.condition}, ${run.weather.temp_f}°F, ${run.weather.humidity}% humidity` : ''}
              </p>
            )}
          </div>
          <button className="close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {err && <div className="banner error">{err}</div>}
        {run && (
          <Body
            run={run}
            onPatch={(patch) => {
              if (patch.hidden) {
                onChanged()
                onClose()
                return
              }
              setRun({ ...run, ...patch, n_comments: (patch.comments ?? run.comments).length })
              onChanged()
            }}
          />
        )}
      </div>
    </div>
  )
}

function Body({ run, onPatch }: { run: RunDetailT; onPatch: (patch: Partial<RunDetailT>) => void }) {
  const zones = run.zones
  const zoneTotal = zones.light_sec + zones.moderate_sec + zones.vigorous_sec + zones.peak_sec
  const splitDomain = paceDomain(run.splits.map((s) => s.pace_sec_mi ?? 0))
  const curveDomain = paceDomain(run.pace_curve.map((p) => p.pace_sec_mi))
  return (
    <>
      <div className="stats-row">
        <Stat label="Distance" value={`${fmtNum(run.distance_mi, 2)} mi`} />
        <Stat label="Time" value={fmtDuration(run.duration_sec)} />
        <Stat label="Pace" value={`${fmtPace(run.pace_sec_mi)} /mi`} />
        <Stat label="Avg HR" value={run.avg_hr ? `${run.avg_hr} bpm` : '–'} />
        <Stat label="Cadence" value={run.cadence_spm ? `${run.cadence_spm} spm` : '–'} />
        <Stat label="Elev. gain" value={run.elevation_gain_ft != null ? `${run.elevation_gain_ft} ft` : '–'} />
      </div>

      <RunNotes runId={run.id} comments={run.comments} excluded={run.excluded_from_model} hidden={run.hidden} onChanged={onPatch} />

      <div className="grid-2" style={{ marginTop: 14 }}>
        <div className="card">
          <div className="card-head">
            <h2>Route</h2>
            {run.heading && <span className="chip">Heads {run.heading}</span>}
          </div>
          <RouteMap lines={[{ points: run.route, color: 'var(--series-1)' }]} />
        </div>

        <div className="card">
          <div className="card-head">
            <h2>Mile splits</h2>
            <p>Pace per mile</p>
          </div>
          {run.splits.length ? (
            <div className="chart" style={{ height: Math.max(140, 28 * run.splits.length + 30) }}>
              <ResponsiveContainer>
                <BarChart data={run.splits} layout="vertical" margin={{ left: 0, right: 48, top: 4, bottom: 4 }} barCategoryGap={4}>
                  <CartesianGrid {...gridProps} horizontal={false} vertical />
                  <XAxis type="number" domain={[0, splitDomain[1]]} tickFormatter={fmtPace} {...axisProps} />
                  <YAxis type="category" dataKey="index" width={28} {...axisProps} tickFormatter={(v) => `${v}`} />
                  <Tooltip cursor={{ fill: 'var(--accent-wash)' }} content={(p: RechartsTip) => splitTip(p, run)} />
                  <Bar dataKey="pace_sec_mi" fill={series.blue} radius={[0, 4, 4, 0]} maxBarSize={20}>
                    <LabelList dataKey="pace_str" position="right" style={{ fill: 'var(--ink-2)', fontSize: 11 }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="empty">No splits recorded.</div>
          )}
        </div>

        {run.pace_curve.length > 0 && (
          <div className="card">
            <div className="card-head">
              <h2>Pace through the run</h2>
              <p>One-minute rolling pace</p>
            </div>
            <div className="chart short">
              <ResponsiveContainer>
                <LineChart data={run.pace_curve} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="dist_mi" type="number" domain={[0, 'dataMax']} tickFormatter={(v) => `${v} mi`} {...axisProps} />
                  <YAxis domain={curveDomain} ticks={paceTicks(curveDomain)} reversed tickFormatter={fmtPace} width={44} {...axisProps} />
                  <Tooltip content={(p: RechartsTip) => (p.active && p.payload?.length ? <Tip title={`${fmtNum(p.payload[0].payload.dist_mi, 2)} mi`} rows={[{ label: 'Pace', value: `${fmtPace(p.payload[0].payload.pace_sec_mi)} /mi` }]} /> : null)} />
                  <Line type="monotone" dataKey="pace_sec_mi" stroke={series.blue} strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {run.hr.length > 0 && (
          <div className="card">
            <div className="card-head">
              <h2>Heart rate</h2>
              <p>Beats per minute over elapsed time</p>
            </div>
            <div className="chart short">
              <ResponsiveContainer>
                <LineChart data={run.hr.map((h) => ({ min: h.sec / 60, bpm: h.bpm }))} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="min" type="number" domain={[0, 'dataMax']} tickFormatter={(v) => `${Math.round(v)}m`} {...axisProps} />
                  <YAxis domain={['dataMin - 10', 'dataMax + 5']} width={36} {...axisProps} />
                  <Tooltip content={(p: RechartsTip) => (p.active && p.payload?.length ? <Tip title={`${fmtNum(p.payload[0].payload.min, 1)} min`} rows={[{ label: 'Heart rate', value: `${p.payload[0].payload.bpm} bpm` }]} /> : null)} />
                  <Line type="monotone" dataKey="bpm" stroke={series.red} strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {zoneTotal > 0 && (
          <div className="card">
            <div className="card-head">
              <h2>Heart rate zones</h2>
              <p>Time in each zone</p>
            </div>
            <div className="zones">
              {[
                ['Peak', zones.peak_sec, 'var(--series-8)'],
                ['Vigorous', zones.vigorous_sec, 'var(--series-2)'],
                ['Moderate', zones.moderate_sec, 'var(--series-4)'],
                ['Light', zones.light_sec, 'var(--series-1)'],
              ].map(([label, sec, color]) => (
                <div className="zone" key={label as string}>
                  <span>{label as string}</span>
                  <div className="bar">
                    <div style={{ width: `${(100 * (sec as number)) / zoneTotal}%`, background: color as string }} />
                  </div>
                  <span className="dur">{fmtDuration(sec as number)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="card">
          <div className="card-head">
            <h2>Details</h2>
          </div>
          <table>
            <tbody>
              <Row k="Calories" v={run.calories ? `${run.calories} kcal` : '–'} />
              <Row k="Stride" v={run.stride_cm ? `${run.stride_cm} cm` : '–'} />
              <Row k="Altitude" v={run.altitude_ft != null ? `${run.altitude_ft} ft` : '–'} />
              <Row k="Feels like" v={run.weather?.feels_like_f != null ? `${run.weather.feels_like_f}°F` : '–'} />
              <Row k="Dew point" v={run.weather?.dew_point_f != null ? `${run.weather.dew_point_f}°F` : '–'} />
              <Row k="Wind" v={run.weather?.wind_mph != null ? `${run.weather.wind_mph} mph` : '–'} />
              <Row k="Source" v={run.source ?? '–'} />
              {run.location_inferred && <Row k="Location" v="No GPS; weather and altitude use a nearby run's start" />}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

function splitTip(p: RechartsTip, run: RunDetailT) {
  if (!p.active || !p.payload?.length) return null
  const s = p.payload[0].payload as RunDetailT['splits'][number]
  return <Tip title={`Mile ${s.index}${s.distance_mi < 0.95 ? ` (${fmtNum(s.distance_mi, 2)} mi)` : ''}`} rows={[{ label: 'Pace', value: `${s.pace_str} /mi` }, { label: 'Time', value: fmtDuration(s.duration_sec) }, { label: 'Run avg', value: `${run.pace_str} /mi` }]} />
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <tr>
      <td className="muted">{k}</td>
      <td className="num">{v}</td>
    </tr>
  )
}
