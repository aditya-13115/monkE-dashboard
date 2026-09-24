import { Bot, Filter, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { SectionHeader } from '../../components/common/UI'
import { seedLivePost } from '../../hooks/useLivePost'
import { apiJson, endpoints } from '../../lib/api'
import { cacheKeys, readCache, writeCache } from '../../lib/cache'
import LivePostCard from './LivePostCard'

export default function SentimentPage({ campaign, setCampaign }) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All')
  const [type, setType] = useState('All')
  const [selectedId, setSelectedId] = useState(() => readCache(cacheKeys.selectedSentimentPost))
  const [overrides, setOverrides] = useState({})
  const [sentiments, setSentiments] = useState({})
  const [loadingIds, setLoadingIds] = useState({})
  const [errors, setErrors] = useState({})

  useEffect(() => {
    const selected = Number(selectedId || 0)
    if (!selected) return
    const cached = readCache(cacheKeys.sentiment(selected))
    if (cached) setSentiments(prev => ({ ...prev, [selected]: cached }))
  }, [selectedId])

  const posts = useMemo(() => {
    const q = query.trim().toLowerCase()
    return campaign.records.filter(post => {
      const okQ = !q || String(post.username || '').toLowerCase().includes(q)
      const okC = category === 'All' || post.category === category
      const okT = type === 'All' || post.postType === type
      return okQ && okC && okT
    })
  }, [campaign.records, query, category, type])

  function updatePost(id, livePost) {
    if (!livePost) return
    seedLivePost(livePost)
    setOverrides(prev => ({ ...prev, [id]: livePost }))
    setCampaign(prev => prev ? ({
      ...prev,
      records: prev.records.map(record => record.id === id ? { ...record, ...livePost } : record),
    }) : prev)
  }

  async function analyzePost(post, force = false) {
    if (!post) return
    const id = post.id
    setSelectedId(id)
    writeCache(cacheKeys.selectedSentimentPost, id)
    setErrors(prev => ({ ...prev, [id]: '' }))

    if (!force) {
      const cached = sentiments[id] || readCache(cacheKeys.sentiment(id))
      if (cached) {
        setSentiments(prev => ({ ...prev, [id]: cached }))
        const cachedPost = cached.post
        if (cachedPost) updatePost(id, cachedPost)
        return
      }
    }

    setLoadingIds(prev => ({ ...prev, [id]: true }))
    try {
      const data = await apiJson(endpoints.sentimentPost(id, force), { method: 'POST' })
      setSentiments(prev => ({ ...prev, [id]: data }))
      writeCache(cacheKeys.sentiment(id), data)
      if (data.post) updatePost(id, data.post)
    } catch (err) {
      setErrors(prev => ({ ...prev, [id]: err?.message || 'Sentiment analysis failed' }))
    } finally {
      setLoadingIds(prev => ({ ...prev, [id]: false }))
    }
  }


  const visiblePosts = posts.map(post => overrides[post.id] || post)

  return (
    <div className="page">
      <SectionHeader
        eyebrow="AI audience voice"
        title="Comment Sentiment"
        copy="Select a campaign post. The exact POST LINK from Excel is opened once, public comments are sampled, and Groq analyzes the sample. Successful results are persisted across browser refreshes."
        action={<div className="live-pill"><span className="status-dot" /> Persistent cache enabled</div>}
      />

      <div className="info-banner">
        <Bot size={18} />
        <div>
          <strong>One post → one shared browser pass</strong>
          <span>Public Instagram metrics, thumbnail and comments are collected together. A previously analyzed post is served from cache instantly; use Re-analyze only when you explicitly want fresh Instagram + Groq work.</span>
        </div>
      </div>

      <div className="toolbar">
        <div className="searchbox"><Search size={15} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search creator username" /></div>
        <div className="selectbox"><Filter size={15} /><select value={category} onChange={event => setCategory(event.target.value)}><option>All</option>{campaign.categories.map(item => <option key={item.name}>{item.name}</option>)}</select></div>
        <div className="selectbox"><select value={type} onChange={event => setType(event.target.value)}><option>All</option><option>Reel</option><option>Post</option></select></div>
        <div className="sentiment-post-count">{visiblePosts.length} posts available</div>
      </div>

      <div className="sentiment-post-grid">
        {visiblePosts.map(post => (
          <LivePostCard
            key={post.id}
            post={post}
            selected={selectedId === post.id}
            analysis={sentiments[post.id]?.analysis}
            analysisLoading={Boolean(loadingIds[post.id])}
            analysisError={errors[post.id]}
            onSelect={selected => { setSelectedId(selected.id); writeCache(cacheKeys.selectedSentimentPost, selected.id) }}
            onLive={updatePost}
            onAnalyze={analyzePost}
          />
        ))}
      </div>

      {!visiblePosts.length && <div className="empty-panel sentiment-empty"><div className="empty-icon"><Search size={28} /></div><h3>No posts match this filter</h3><p>Adjust the creator, category or post-type filter.</p></div>}
    </div>
  )
}
