import type { ReactNode } from 'react'

/** Shared chart chrome: colors read from CSS tokens, recessive axes, one tooltip style. */

export const axisProps = {
  tick: { fill: 'var(--ink-3)', fontSize: 11 },
  axisLine: { stroke: 'var(--axis)' },
  tickLine: false as const,
}

export const gridProps = { stroke: 'var(--grid)', vertical: false }

export const series = {
  blue: 'var(--series-1)',
  orange: 'var(--series-2)',
  aqua: 'var(--series-3)',
  yellow: 'var(--series-4)',
  violet: 'var(--series-7)',
  red: 'var(--series-8)',
  muted: 'var(--axis)',
}

export interface TipRow {
  label: string
  value: ReactNode
}

export function Tip({ title, rows }: { title: ReactNode; rows: TipRow[] }) {
  return (
    <div className="tooltip">
      <div className="t">{title}</div>
      {rows.map((r, i) => (
        <div className="r" key={i}>
          <span>{r.label}</span>
          <b>{r.value}</b>
        </div>
      ))}
    </div>
  )
}

// Loose tooltip props: recharts' generic ContentType is awkward to satisfy exactly.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type RechartsTip = { active?: boolean; payload?: ReadonlyArray<any> } & Record<string, any>

/** Scatter click handlers receive the point item; the run lives on its payload. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function clickedRunId(d: any): string | undefined {
  const r = d?.payload?.run ?? d?.run
  return r?.id
}

export function Legend({ items }: { items: { color: string; label: string; dot?: boolean }[] }) {
  return (
    <div className="legend">
      {items.map((it) => (
        <span className="key" key={it.label}>
          <span className={`swatch${it.dot ? ' dot' : ''}`} style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  )
}

/** Sequential blue for pace heat (fast = dark). */
export function paceColor(sec: number, min: number, max: number): string {
  const steps = ['var(--seq-100)', 'var(--seq-250)', 'var(--seq-400)', 'var(--seq-550)', 'var(--seq-700)']
  if (max <= min) return steps[2]
  const t = 1 - (sec - min) / (max - min)
  return steps[Math.max(0, Math.min(steps.length - 1, Math.round(t * (steps.length - 1))))]
}

/** Round a pace axis domain to clean 30-second bounds. */
export function paceDomain(values: number[]): [number, number] {
  const v = values.filter((x) => x != null && isFinite(x))
  if (!v.length) return [420, 660]
  const lo = Math.floor((Math.min(...v) - 15) / 30) * 30
  const hi = Math.ceil((Math.max(...v) + 15) / 30) * 30
  return [lo, hi]
}

export function paceTicks([lo, hi]: [number, number], step = 30): number[] {
  const out: number[] = []
  for (let v = lo; v <= hi; v += step) out.push(v)
  return out.length > 9 ? paceTicks([lo, hi], step * 2) : out
}
