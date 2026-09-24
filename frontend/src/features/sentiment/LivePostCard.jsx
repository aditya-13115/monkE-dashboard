import { Activity, ExternalLink, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { LiveBadge, Pill, PostThumbnail } from '../../components/common/UI'
import { useLivePost } from '../../hooks/useLivePost'
import { fmt, pct } from '../../lib/metrics'
import SentimentInlineAnalysis from './SentimentInlineAnalysis'

export default function LivePostCard({
  post,
  selected,
  analysis,
  analysisLoading,
  analysisError,
  onSelect,
  onLive,
  onAnalyze,
}) {
  const [loadingLive, setLoadingLive] = useState(false)
  const [localError, setLocalError] = useState('')
  const { fetchLivePost } = useLivePost()

  async function refreshLive(event) {
    event.stopPropagation()
    setLoadingLive(true)
    setLocalError('')
    try {
      const result = await fetchLivePost(post.id, true)
      onLive(post.id, result)
    } catch (err) {
      setLocalError(err?.message || 'Live refresh failed')
    } finally {
      setLoadingLive(false)
    }
  }

  const reach = Number(post.reach || 0)
  const engagement = Number(post.liveDataAvailable ? post.liveEngagement : post.engagement || 0)
  const likes = Number(post.liveLikes || 0)
  const comments = Number(post.liveComments || 0)
  const views = Number(post.liveViews || 0)
  const er = reach ? (engagement / reach) * 100 : Number(post.engagementRateReach || 0)

  function selectPost() {
    onSelect(post)
    onAnalyze(post, false)
  }

  return (
    <article className={`sentiment-post-card ${selected ? 'selected' : ''}`} onClick={selectPost}>
      <div className="sentiment-card-main">
        <PostThumbnail post={post} />
        <div className="sentiment-post-body">
          <div className="sentiment-post-topline">
            <strong>@{post.username}</strong>
            <span>{post.category}</span>
          </div>
          <div className="sentiment-post-metrics">
            <span><b>{fmt(reach)}</b> reach</span>
            <span><b>{fmt(engagement)}</b> eng.</span>
            {likes > 0 && <span><b>{fmt(likes)}</b> likes</span>}
            {comments > 0 && <span><b>{fmt(comments)}</b> cmts</span>}
            {views > 0 && <span><b>{fmt(views)}</b> views</span>}
          </div>
          <div className="sentiment-card-status">
            {post.liveDataAvailable ? <LiveBadge cached={post.liveCacheHit !== false} age={post.liveCacheAgeSeconds} /> : <span>Workbook metrics</span>}
            <span>{pct(er)} ER</span>
          </div>
          {post.liveDataAvailable && <small className="live-cache-age">{post.liveCacheAgeSeconds ? `cached ${Math.round(post.liveCacheAgeSeconds / 60)}m ago` : 'just synced'}</small>}
          {localError && <small className="live-card-error">{localError}</small>}
        </div>
      </div>

      {selected && (
        <div className="selected-card-toolbar" onClick={event => event.stopPropagation()}>
          <div>
            <div className="eyebrow">Selected post</div>
            <strong>@{post.username}</strong>
            <Pill>{analysisLoading ? 'Analyzing…' : analysis ? 'Analysis cached' : 'Ready'}</Pill>
          </div>
          <div className="selected-post-actions">
            <button className="ghost-btn" onClick={refreshLive} disabled={loadingLive}><Activity size={13} className={loadingLive ? 'spin' : ''} /> {loadingLive ? 'Refreshing…' : 'Refresh live'}</button>
            <a className="ghost-btn" href={post.postLink} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Open post</a>
          </div>
        </div>
      )}

      {selected && (
        <div onClick={event => event.stopPropagation()}>
          <SentimentInlineAnalysis analysis={analysis} loading={analysisLoading} error={analysisError} onReanalyze={() => onAnalyze(post, true)} />
        </div>
      )}

      {!selected && (
        <div className="sentiment-card-cta"><span>Click to analyze audience voice</span><span>→</span></div>
      )}
    </article>
  )
}
