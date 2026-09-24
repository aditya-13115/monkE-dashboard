import { Instagram } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fmt, initials } from '../../lib/metrics'

export function Metric({ icon: Icon, label, value, sub, accent }) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <div className={`metric-icon ${accent || ''}`}><Icon size={16} /></div>
        <span>{label}</span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-sub">{sub}</div>
    </div>
  )
}

export function SectionHeader({ eyebrow, title, copy, action }) {
  return (
    <div className="section-head">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h2>{title}</h2>
        {copy && <p>{copy}</p>}
      </div>
      {action}
    </div>
  )
}

export function Pill({ children, tone = '' }) {
  return <span className={`pill ${tone}`}>{children}</span>
}

export function LiveBadge({ cached = false, age = null }) {
  return (
    <span className="live-badge" title={age == null ? 'Live public Instagram data' : `Instagram data ${age} old`}>
      <span className="live-dot" />
      {cached ? 'Cached live' : 'Instagram live'}
    </span>
  )
}

export function Loader({ label = 'Loading…', mini = false }) {
  return <div className={mini ? 'inline-loader' : 'loading'}><div className="loader" />{label}</div>
}

export function PostThumbnail({ post }) {
  const [failed, setFailed] = useState(false)
  const ImageIcon = Instagram
  const src = typeof post?.thumbnailUrl === 'string' && /^https?:\/\//i.test(post.thumbnailUrl)
    ? post.thumbnailUrl
    : ''

  useEffect(() => setFailed(false), [src])

  return (
    <div className="sentiment-thumb">
      {src && !failed ? (
        <img
          src={src}
          alt={`@${post?.username || 'instagram'} ${post?.postType || 'post'}`}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : null}
      {(failed || !src) && (
        <div className="sentiment-thumb-fallback">
          <div className="instagram-glyph"><ImageIcon size={22} /></div>
          <strong>@{post?.username}</strong>
          <span>{post?.postType || 'Post'}</span>
        </div>
      )}
      <div className="sentiment-thumb-overlay">
        <Instagram size={13} />
        <span>{post?.postType || 'Post'}</span>
      </div>
    </div>
  )
}

export function Avatar({ username }) {
  return <div className="avatar">{initials(username)}</div>
}

export { fmt }
