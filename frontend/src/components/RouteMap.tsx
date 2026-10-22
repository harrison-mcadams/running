import { useEffect, useMemo } from 'react'
import { MapContainer, Polyline, TileLayer, CircleMarker, useMap } from 'react-leaflet'
import L from 'leaflet'
import type { LatLon } from '../api'

interface Line {
  points: LatLon[]
  color: string
  weight?: number
  opacity?: number
}

function FitBounds({ lines }: { lines: Line[] }) {
  const map = useMap()
  useEffect(() => {
    const pts = lines.flatMap((l) => l.points.map((p) => [p.lat, p.lon] as [number, number]))
    if (pts.length) map.fitBounds(L.latLngBounds(pts), { padding: [20, 20] })
  }, [map, lines])
  return null
}

const isDark = () => window.matchMedia?.('(prefers-color-scheme: dark)').matches

export function RouteMap({ lines, className = 'map', showStart = true }: { lines: Line[]; className?: string; showStart?: boolean }) {
  const dark = useMemo(isDark, [])
  const first = lines.find((l) => l.points.length)
  if (!first) return <div className={`${className} empty`}>No GPS track for this run.</div>
  const start = first.points[0]
  return (
    <div className={className}>
      <MapContainer center={[start.lat, start.lon]} zoom={13} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
        <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} className={dark ? 'tiles-dark' : undefined} attribution="&copy; OpenStreetMap contributors" />
        {lines.map((l, i) => (
          <Polyline key={i} positions={l.points.map((p) => [p.lat, p.lon] as [number, number])} pathOptions={{ color: l.color, weight: l.weight ?? 3, opacity: l.opacity ?? 0.9, lineJoin: 'round' }} />
        ))}
        {showStart && (
          <CircleMarker center={[start.lat, start.lon]} radius={5} pathOptions={{ color: '#fff', weight: 2, fillColor: first.color, fillOpacity: 1 }} />
        )}
        <FitBounds lines={lines} />
      </MapContainer>
    </div>
  )
}
