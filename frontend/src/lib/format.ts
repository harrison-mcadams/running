export function fmtPace(sec: number | null | undefined): string {
  if (sec == null || !isFinite(sec) || sec <= 0) return '–'
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return s === 60 ? `${m + 1}:00` : `${m}:${s.toString().padStart(2, '0')}`
}

export function fmtDuration(sec: number | null | undefined): string {
  if (sec == null) return '–'
  const s = Math.round(sec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  return h ? `${h}:${m.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}` : `${m}:${r.toString().padStart(2, '0')}`
}

export function fmtSigned(sec: number, digits = 0): string {
  const v = sec.toFixed(digits)
  return sec > 0 ? `+${v}` : v
}

export function fmtDate(iso: string, opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }): string {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, opts)
}

export function fmtDateLong(iso: string): string {
  return fmtDate(iso, { weekday: 'short', month: 'long', day: 'numeric', year: 'numeric' })
}

export function fmtTime12(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number)
  const suffix = h >= 12 ? 'pm' : 'am'
  const hh = h % 12 === 0 ? 12 : h % 12
  return `${hh}:${m.toString().padStart(2, '0')} ${suffix}`
}

export function hourLabel(h: number): string {
  const whole = Math.floor(h)
  const suffix = whole >= 12 ? 'pm' : 'am'
  const hh = whole % 12 === 0 ? 12 : whole % 12
  return `${hh}${suffix}`
}

export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || !isFinite(v)) return '–'
  return v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

export function toDayNumber(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return Date.UTC(y, m - 1, d) / 86400000
}

export function dayNumberToIso(n: number): string {
  return new Date(n * 86400000).toISOString().slice(0, 10)
}

export function mean(xs: number[]): number | null {
  const v = xs.filter((x) => x != null && isFinite(x))
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
}

export function linearTrend(xs: number[], ys: number[]): { slope: number; intercept: number } | null {
  const n = xs.length
  if (n < 2) return null
  const mx = xs.reduce((a, b) => a + b, 0) / n
  const my = ys.reduce((a, b) => a + b, 0) / n
  let num = 0
  let den = 0
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (ys[i] - my)
    den += (xs[i] - mx) ** 2
  }
  if (den === 0) return null
  const slope = num / den
  return { slope, intercept: my - slope * mx }
}

/** A split shorter than this is a partial mile: its GPS pace is unreliable (cool-down, stop lag). */
export const FULL_SPLIT_MI = 0.9
/** Trailing splits shorter than this are recording artifacts (the watch ran on after you stopped). */
export const STUB_SPLIT_MI = 0.1
