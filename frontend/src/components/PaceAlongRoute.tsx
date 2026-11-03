import { useEffect, useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type GroupMember } from '../api'
import { fmtNum, fmtPace } from '../lib/format'
import { axisProps, gridProps, Legend, paceDomain, paceTicks, series, Tip, type RechartsTip } from './charts'

type Profiles = Record<string, [number, number][]>

interface Row {
  x: number
  focus?: number
  avg?: number
  n: number
  [other: `o${number}`]: number | undefined
}

/** Continuous pace vs distance: the selected run, the average of the similar runs at each point,
 *  and each similar run as a faint line. Profiles come from the server on a shared 0.05 mi grid. */
export function PaceAlongRoute({ groupId, focus, others, version }: { groupId: number; focus: GroupMember; others: GroupMember[]; version: number }) {
  const [profiles, setProfiles] = useState<Profiles | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    api
      .groupProfiles(groupId)
      .then((r) => live && setProfiles(r.profiles))
      .catch((e) => live && setErr(String(e)))
    return () => {
      live = false
    }
  }, [groupId, version])

  const rows = useMemo(() => {
    if (!profiles) return []
    const byX = new Map<number, Row>()
    const at = (x: number) => {
      const k = Math.round(x * 100)
      let r = byX.get(k)
      if (!r) {
        r = { x: k / 100, n: 0 }
        byX.set(k, r)
      }
      return r
    }
    for (const [x, p] of profiles[focus.id] ?? []) at(x).focus = p
    const sums = new Map<number, number>()
    others.forEach((o, i) => {
      for (const [x, p] of profiles[o.id] ?? []) {
        const r = at(x)
        r[`o${i}`] = p
        r.n += 1
        sums.set(Math.round(x * 100), (sums.get(Math.round(x * 100)) ?? 0) + p)
      }
    })
    for (const [k, r] of byX) if (r.n) r.avg = Math.round((sums.get(k) ?? 0) / r.n)
    return [...byX.values()].sort((a, b) => a.x - b.x)
  }, [profiles, focus.id, others])

  if (err) return <div className="banner error">{err}</div>
  if (!profiles) return <div className="empty">Loading pace profiles…</div>
  if (!profiles[focus.id]?.length) return <div className="empty">No GPS distance stream for the selected run.</div>

  // Scale to the selected run and the average; individual runs may spike off-chart.
  const domain = paceDomain(rows.flatMap((r) => [r.focus, r.avg]).filter((v): v is number => v != null))
  const xMax = Math.ceil(Math.max(...rows.map((r) => r.x)) * 2) / 2

  return (
    <>
      <div className="chart tall">
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="x" type="number" domain={[0, xMax]} tickFormatter={(v) => `${v} mi`} {...axisProps} />
            <YAxis domain={domain} ticks={paceTicks(domain)} reversed allowDataOverflow tickFormatter={fmtPace} width={44} {...axisProps} />
            <Tooltip
              cursor={{ stroke: 'var(--axis)' }}
              content={(p: RechartsTip) => {
                if (!p.active || !p.payload?.length) return null
                const r = p.payload[0].payload as Row
                return (
                  <Tip
                    title={`${fmtNum(r.x, 2)} mi`}
                    rows={[
                      { label: 'Selected', value: r.focus != null ? `${fmtPace(r.focus)} /mi` : '–' },
                      { label: r.n ? `Average of ${r.n}` : 'Average', value: r.avg != null ? `${fmtPace(r.avg)} /mi` : '–' },
                      ...(r.focus != null && r.avg != null ? [{ label: 'Difference', value: `${r.focus - r.avg > 0 ? '+' : ''}${r.focus - r.avg} s` }] : []),
                    ]}
                  />
                )
              }}
            />
            {others.map((o, i) => (
              <Line key={o.id} dataKey={`o${i}`} stroke={series.blue} strokeOpacity={0.3} strokeWidth={1} dot={false} activeDot={false} isAnimationActive={false} connectNulls={false} />
            ))}
            <Line dataKey="avg" stroke={series.blue} strokeWidth={2.5} dot={false} isAnimationActive={false} connectNulls={false} />
            <Line dataKey="focus" stroke={series.orange} strokeWidth={2.5} dot={false} isAnimationActive={false} connectNulls={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Legend
        items={[
          { color: series.orange, label: 'Selected run' },
          { color: series.blue, label: `Average of ${others.length} similar run${others.length === 1 ? '' : 's'}` },
          { color: 'color-mix(in srgb, var(--series-1) 40%, transparent)', label: 'Each similar run' },
        ]}
      />
      <p className="note">Pace is smoothed over 0.2 mi and leaves out time spent stopped. Runs line up by distance from the start, so pick one direction out for a like-for-like comparison.</p>
    </>
  )
}
