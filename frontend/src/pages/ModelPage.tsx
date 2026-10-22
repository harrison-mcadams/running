import { useEffect, useMemo, useRef, useState } from 'react'
import { CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceDot, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { api, type Conditions, type FeatureRow, type ModelSummary, type Prediction, type TimelineRun } from '../api'
import { dayNumberToIso, fmtDate, fmtNum, fmtPace, fmtSigned, hourLabel, toDayNumber } from '../lib/format'
import { axisProps, gridProps, Legend, paceDomain, paceTicks, series, Tip, type RechartsTip } from '../components/charts'

type Variant = 'conditions' | 'effort'

export function ModelPage({ version }: { version: number }) {
  const [variant, setVariant] = useState<Variant>('conditions')
  const [model, setModel] = useState<ModelSummary | null>(null)
  const [conditions, setConditions] = useState<Conditions | null>(null)
  const [inputs, setInputs] = useState<Record<string, number>>({})
  const [pred, setPred] = useState<Prediction | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const seeded = useRef(false)

  useEffect(() => {
    setModel(null)
    api.model(variant).then(setModel).catch((e) => setErr(String(e)))
  }, [variant, version])

  useEffect(() => {
    api.conditions().then(setConditions).catch(() => null)
  }, [version])

  // Seed the form from today's conditions once the model and conditions are known.
  useEffect(() => {
    if (!model?.ok || !conditions || seeded.current) return
    const next: Record<string, number> = {}
    for (const f of model.features) {
      const c = (conditions as unknown as Record<string, number | null>)[f.key]
      next[f.key] = f.key === 'weeks' ? model.last_run.weeks + weeksSince(model.timeline.runs.at(-1)?.date, conditions.date) : c != null ? c : f.baseline
    }
    setInputs(next)
    seeded.current = true
  }, [model, conditions])

  // Fill any inputs the current variant needs but the form lacks (e.g. heart rate on switch).
  useEffect(() => {
    if (!model?.ok) return
    setInputs((cur) => {
      const next = { ...cur }
      let changed = false
      for (const f of model.features) if (next[f.key] == null) { next[f.key] = f.baseline; changed = true }
      return changed ? next : cur
    })
  }, [model])

  const debounced = useDebounced(inputs, 150)
  useEffect(() => {
    if (!model?.ok || !Object.keys(debounced).length) return
    api.predict(variant, debounced).then(setPred).catch((e) => setErr(String(e)))
  }, [debounced, variant, model])

  if (err) return <div className="banner error">{err}</div>
  if (!model) return <div className="empty">Fitting the model…</div>
  if (!model.ok) return <div className="empty">{model.reason}</div>

  const t = model.timeline
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pace model</h1>
          <p>A linear model of your pace fitted to {model.n_runs} runs{model.n_excluded ? ` (${model.n_excluded} excluded by you)` : ''}: what each factor costs, what you would run today, and whether you are getting faster once conditions are taken out.</p>
        </div>
        <div className="seg">
          <button className={variant === 'conditions' ? 'active' : ''} onClick={() => setVariant('conditions')}>Conditions only</button>
          <button className={variant === 'effort' ? 'active' : ''} onClick={() => setVariant('effort')}>Control for heart rate</button>
        </div>
      </div>

      <div className="tiles">
        <Tile label="Typical error" value={`±${fmtNum(model.mae_loo_sec)} s/mi`} sub="leave-one-out, so honest about new runs" />
        <Tile label="Explained" value={`${Math.round(model.r2_loo * 100)}%`} sub={`of pace variation out of sample (${Math.round(model.r2_in_sample * 100)}% in sample)`} />
        <Tile label="Fitness trend" value={`${fmtSigned(t.trend_sec_per_month, 1)} s/mi`} sub={`per month, conditions held fixed (${t.trend_sec_per_month < 0 ? 'getting faster' : 'getting slower'})`} tone={t.trend_sec_per_month < 0 ? 'good' : t.trend_sec_per_month > 0 ? 'bad' : undefined} />
        <Tile label="Baseline run" value={`${fmtPace(model.baseline_pace_sec)} /mi`} sub={`${fmtNum(model.baseline.distance_mi, 1)} mi at ${Math.round(model.baseline.temp_f)}°F, ${Math.round(model.baseline.humidity)}%`} />
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-head">
          <h2>What moves your pace</h2>
          <p>Effect of a typical swing in each factor (its middle 50% range), with an 80% bootstrap interval. Right is slower.</p>
        </div>
        <Coefficients features={model.features} />
        <p className="note">
          {variant === 'effort'
            ? 'With heart rate in the model, each coefficient is the effect at a fixed effort level.'
            : 'Factors whose interval straddles zero are not distinguishable from no effect with this many runs. Altitude and hilliness only sharpen once you have runs that vary in them.'}
        </p>
      </div>

      <div className="grid-2" style={{ marginTop: 14 }}>
        <div className="card">
          <div className="card-head">
            <h2>Plan a run</h2>
            <p>Starts from today's conditions at your usual start point.</p>
          </div>
          <div className="form-grid">
            {model.features.map((f) => (
              <SliderField key={f.key} f={f} value={inputs[f.key] ?? f.baseline} onChange={(v) => setInputs((cur) => ({ ...cur, [f.key]: v }))} />
            ))}
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <h2>Expected pace</h2>
            {pred?.ok && <p>80% of runs land within the range</p>}
          </div>
          {pred?.ok ? (
            <>
              <div className="hero">{pred.pace_str} <span style={{ fontSize: 18, fontWeight: 500, color: 'var(--ink-2)' }}>/mi</span></div>
              <p className="muted" style={{ margin: '4px 0 12px' }}>
                {fmtPace(pred.low_sec)} – {fmtPace(pred.high_sec)} · baseline run {fmtPace(pred.baseline_pace_sec)}
              </p>
              <h3 style={{ marginBottom: 6 }}>Versus the baseline run</h3>
              <div className="chips">
                {model.features
                  .map((f) => ({ f, v: pred.contributions[f.key] ?? 0 }))
                  .filter((x) => Math.abs(x.v) >= 0.5)
                  .sort((a, b) => Math.abs(b.v) - Math.abs(a.v))
                  .map(({ f, v }) => (
                    <span key={f.key} className={`chip ${v > 0 ? 'plus' : 'minus'}`}>
                      {f.label} {fmtSigned(v)} s
                    </span>
                  ))}
                {model.features.every((f) => Math.abs(pred.contributions[f.key] ?? 0) < 0.5) && <span className="chip">Same as the baseline run</span>}
              </div>
              <h3 style={{ margin: '16px 0 6px' }}>If one thing changed</h3>
              <div className="grid-2" style={{ gap: 10 }}>
                {model.features.filter((f) => f.active).map((f) => (
                  <Sensitivity key={f.key} f={f} curve={pred.curves[f.key] ?? []} x={pred.inputs[f.key]} y={pred.pace_sec} />
                ))}
              </div>
            </>
          ) : (
            <div className="empty">Predicting…</div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-head">
          <h2>Are you getting faster?</h2>
          <p>Each run's pace adjusted to baseline conditions, so only fitness remains. Faster is up.</p>
        </div>
        <Timeline runs={t.runs} />
        <p className="note">
          Over the record the adjusted trend moved {fmtNum(Math.abs(t.trend_total_sec))} s/mi {t.trend_total_sec < 0 ? 'faster' : 'slower'} ({fmtSigned(t.trend_sec_per_month, 1)} s/mi per month).
        </p>
        <details style={{ marginTop: 10 }}>
          <summary>Per-run adjustments</summary>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th className="num">Actual</th>
                  <th className="num">Adjusted</th>
                  <th className="num">Predicted</th>
                  {model.features.filter((f) => f.key !== 'weeks').map((f) => (
                    <th key={f.key} className="num">{f.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...t.runs].reverse().map((r) => (
                  <tr key={r.id}>
                    <td>{fmtDate(r.date, { month: 'short', day: 'numeric', year: '2-digit' })}</td>
                    <td className="num">{fmtPace(r.actual_sec)}</td>
                    <td className="num">{fmtPace(r.adjusted_sec)}</td>
                    <td className="num muted">{fmtPace(r.predicted_sec)}</td>
                    {model.features.filter((f) => f.key !== 'weeks').map((f) => (
                      <td key={f.key} className={`num ${Math.abs(r.adjustments[f.key] ?? 0) < 0.5 ? 'muted' : ''}`}>{fmtSigned(r.adjustments[f.key] ?? 0)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="note">Adjustment columns are seconds per mile added to the actual pace to remove that factor's effect.</p>
        </details>
      </div>
    </>
  )
}

function clockLabel(h: number): string {
  const whole = Math.floor(h)
  const mins = Math.round((h - whole) * 60)
  const hh = whole % 12 === 0 ? 12 : whole % 12
  return `${hh}:${String(mins).padStart(2, '0')} ${whole >= 12 ? 'pm' : 'am'}`
}

function weeksSince(from: string | undefined, to: string): number {
  if (!from) return 0
  return Math.max(0, (toDayNumber(to) - toDayNumber(from)) / 7)
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
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

function Coefficients({ features }: { features: FeatureRow[] }) {
  const extent = Math.max(5, ...features.flatMap((f) => [Math.abs(f.ci_low * f.iqr), Math.abs(f.ci_high * f.iqr), Math.abs(f.typical_swing_sec)]))
  const pos = (v: number) => `${50 + (50 * Math.max(-extent, Math.min(extent, v))) / extent}%`
  return (
    <div>
      {features.map((f) => {
        const lo = f.ci_low * f.iqr
        const hi = f.ci_high * f.iqr
        const sure = lo > 0 || hi < 0
        if (!f.active)
          return (
            <div className="coef-row" key={f.key} title={f.description} style={{ opacity: 0.6 }}>
              <div className="label">
                <b>{f.label}</b>
                <span>not fitted yet</span>
              </div>
              <div className="small muted">Your runs only span {fmtNum(f.observed[0], 1)}–{fmtNum(f.observed[1], 1)} {f.unit}; it joins the model once they vary more.</div>
              <div className="num muted">–</div>
            </div>
          )
        return (
          <div className="coef-row" key={f.key} title={f.description}>
            <div className="label">
              <b>{f.label}</b>
              <span>
                {fmtSigned(f.coef_sec_per_unit, Math.abs(f.coef_sec_per_unit) < 1 ? 2 : 1)} s/mi per {f.unit} · swing {fmtNum(f.iqr, f.iqr < 2 ? 1 : 0)} {f.unit}
              </span>
            </div>
            <div className="coef-track">
              <div className="zero" style={{ left: '50%' }} />
              <div className="ci" style={{ left: pos(Math.min(lo, hi)), width: `calc(${pos(Math.max(lo, hi))} - ${pos(Math.min(lo, hi))})` }} />
              <div className="pt" style={{ left: pos(f.typical_swing_sec), background: sure ? 'var(--series-1)' : 'var(--ink-3)' }} />
            </div>
            <div className="num" style={{ color: sure ? 'var(--ink)' : 'var(--ink-3)' }}>{fmtSigned(f.typical_swing_sec)} s</div>
          </div>
        )
      })}
    </div>
  )
}

function SliderField({ f, value, onChange }: { f: FeatureRow; value: number; onChange: (v: number) => void }) {
  const [lo, hi] = f.range
  const step = f.key === 'local_hour' ? 0.25 : hi - lo > 50 ? 1 : hi - lo > 10 ? 0.5 : 0.1
  const display = f.key === 'local_hour' ? clockLabel(value) : f.key === 'weeks' ? `${fmtNum(value, 0)} wk` : `${fmtNum(value, step < 1 ? 1 : 0)} ${f.unit}`
  return (
    <label className="slider" title={f.active ? f.description : 'Not in the model yet: your runs do not vary in this.'} style={f.active ? undefined : { opacity: 0.5 }}>
      <span>{f.label}{f.active ? '' : ' (no variation yet)'}</span>
      <span className="val">{display}</span>
      <input type="range" min={lo} max={hi} step={step} value={value} disabled={!f.active} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  )
}

function Sensitivity({ f, curve, x, y }: { f: FeatureRow; curve: { x: number; pace_sec: number; observed: boolean }[]; x: number; y: number }) {
  if (!curve.length) return null
  const [obsLo, obsHi] = f.observed
  const domain = paceDomain([...curve.map((c) => c.pace_sec), y])
  const fmtX = (v: number) => (f.key === 'local_hour' ? hourLabel(v) : `${fmtNum(v, f.range[1] - f.range[0] > 20 ? 0 : 1)}`)
  return (
    <div>
      <div className="small" style={{ color: 'var(--ink-2)', marginBottom: 2 }}>
        {f.label} <span className="muted">({f.unit})</span>
      </div>
      <div className="chart" style={{ height: 120 }}>
        <ResponsiveContainer>
          <ComposedChart data={curve} margin={{ left: 0, right: 8, top: 6, bottom: 0 }}>
            <ReferenceArea x1={obsLo} x2={obsHi} fill="var(--accent-wash)" stroke="none" />
            <XAxis dataKey="x" type="number" domain={[f.range[0], f.range[1]]} tickFormatter={fmtX} {...axisProps} tickCount={4} />
            <YAxis domain={domain} ticks={paceTicks(domain, 60)} reversed tickFormatter={fmtPace} width={40} {...axisProps} />
            <Tooltip content={(p: RechartsTip) => (p.active && p.payload?.length ? <Tip title={`${f.label} ${fmtX(p.payload[0].payload.x)}`} rows={[{ label: 'Pace', value: fmtPace(p.payload[0].payload.pace_sec) }]} /> : null)} />
            <Line type="monotone" dataKey="pace_sec" stroke={series.blue} strokeWidth={2} dot={false} isAnimationActive={false} />
            <ReferenceDot x={x} y={y} r={5} fill={series.orange} stroke="var(--surface)" strokeWidth={2} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="small muted">Shaded: the range your runs cover</div>
    </div>
  )
}

function Timeline({ runs }: { runs: TimelineRun[] }) {
  const data = useMemo(() => runs.map((r) => ({ x: toDayNumber(r.date), actual: r.actual_sec, adjusted: r.adjusted_sec, smoothed: r.smoothed_sec, trend: r.trend_sec, run: r })), [runs])
  if (!data.length) return null
  const domain = paceDomain(data.flatMap((d) => [d.actual, d.adjusted]))
  const [x0, x1] = [data[0].x, data[data.length - 1].x]
  return (
    <>
      <div className="chart tall">
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="x" type="number" domain={[x0 - 5, x1 + 5]} tickFormatter={(v) => fmtDate(dayNumberToIso(v))} {...axisProps} />
            <YAxis domain={domain} ticks={paceTicks(domain)} reversed tickFormatter={fmtPace} width={44} {...axisProps} />
            <ZAxis range={[50, 50]} />
            <Tooltip
              cursor={false}
              content={(p: RechartsTip) => {
                if (!p.active || !p.payload?.length) return null
                const r = (p.payload[0].payload as { run: TimelineRun }).run
                return <Tip title={fmtDate(r.date, { weekday: 'short', month: 'short', day: 'numeric' })} rows={[{ label: 'Actual', value: fmtPace(r.actual_sec) }, { label: 'Adjusted', value: fmtPace(r.adjusted_sec) }, { label: 'Fitness (smoothed)', value: fmtPace(r.smoothed_sec) }, { label: 'Distance', value: `${fmtNum(r.distance_mi, 1)} mi` }]} />
              }}
            />
            <Line dataKey="trend" stroke="var(--ink-3)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="smoothed" stroke={series.blue} strokeWidth={2} dot={false} isAnimationActive={false} />
            <Scatter dataKey="actual" fill="var(--axis)" stroke="var(--surface)" strokeWidth={2} isAnimationActive={false} />
            <Scatter dataKey="adjusted" fill={series.blue} stroke="var(--surface)" strokeWidth={2} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <Legend items={[{ color: series.blue, label: 'Adjusted pace', dot: true }, { color: 'var(--axis)', label: 'Actual pace', dot: true }, { color: series.blue, label: 'Fitness (smoothed adjusted)' }, { color: 'var(--ink-3)', label: 'Linear trend' }]} />
    </>
  )
}
