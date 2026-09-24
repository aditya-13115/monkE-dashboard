export const fmt = n => {
  const v = Number(n || 0)
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)}B`
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(v >= 10e6 ? 1 : 2)}M`
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(v >= 100e3 ? 0 : 1)}K`
  return new Intl.NumberFormat('en-IN').format(v)
}

export const pct = n => `${Number(n || 0).toFixed(2)}%`

export const initials = name => String(name || 'IG').replace(/^@/, '').slice(0, 2).toUpperCase()

export const publicEngagement = post => {
  const live = Number(post?.liveEngagement)
  return post?.liveDataAvailable && Number.isFinite(live) ? live : Number(post?.engagement || 0)
}

export const publicViews = post => Number(post?.liveViews || 0)

export const isLive = post => Boolean(post?.liveDataAvailable)

export function ageLabel(seconds) {
  if (seconds == null) return ''
  const sec = Math.max(0, Number(seconds) || 0)
  if (sec < 60) return `${Math.round(sec)}s ago`
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`
  return `${Math.round(sec / 86400)}d ago`
}
