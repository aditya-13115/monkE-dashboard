import { BarChart3, Eye, FileSpreadsheet, MessageCircle, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell } from 'recharts'
import { Metric, Pill, PostThumbnail } from '../../components/common/UI'
import { apiJson, endpoints } from '../../lib/api'
import { fmt, pct } from '../../lib/metrics'
import CampaignSentimentPanel from '../campaignSentiment/CampaignSentimentPanel'

const palette = ['#8b5cf6', '#10b981', '#3b82f6', '#f59e0b', '#f43f5e', '#14b8a6']

function readToken() {
  const match = window.location.pathname.match(/^\/share\/([^/]+)/)
  return match?.[1] || ''
}

function aggregate(campaigns) {
  const records = campaigns.flatMap(c => c.records || [])
  const total = (key) => records.reduce((sum, row) => sum + Number(row[key] || 0), 0)
  const live = records.filter(row => row.liveDataAvailable)
  return {
    posts: records.length,
    followers: total('followers'),
    reach: total('reach'),
    engagement: total('engagement'),
    liveLikes: total('liveLikes'),
    liveViews: total('liveViews'),
    liveEngagement: live.reduce((sum, row) => sum + Number(row.liveEngagement || 0), 0),
    liveCoverage: records.length ? live.length / records.length * 100 : 0,
  }
}

export default function ViewerApp() {
  const token = readToken()
  const [data, setData] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    apiJson(endpoints.publicShare(token))
      .then(payload => { if (alive) { setData(payload); setSelectedId(payload.campaigns?.[0]?.meta?.campaign ? payload.campaigns[0].records?.[0]?.campaignId : null) } })
      .catch(err => { if (alive) setError(err?.message || 'Share link unavailable') })
    return () => { alive = false }
  }, [token])

  const selectedCampaign = useMemo(() => {
    if (!data?.campaigns?.length) return null
    if (!selectedId) return data.campaigns[0]
    return data.campaigns.find(c => c.records?.[0]?.campaignId === selectedId) || data.campaigns[0]
  }, [data, selectedId])

  if (error) return <div className="viewer-error"><strong>Read-only view unavailable</strong><span>{error}</span></div>
  if (!data) return <div className="viewer-loading"><div className="loader" /><span>Loading shared campaign view…</span></div>

  const campaigns = data.campaigns || []
  const active = selectedCampaign || campaigns[0]
  const summary = aggregate([active])
  const categories = (active.categories || []).map((row, index) => ({ ...row, liveViews: Number(row.liveViews || 0), liveEngagement: Number(row.liveEngagement || 0), fill: palette[index % palette.length] }))
  const topPosts = [...(active.records || [])].sort((a, b) => Number(b.liveViews || 0) - Number(a.liveViews || 0)).slice(0, 8)

  return (
    <div className="viewer-shell">
      <header className="viewer-topbar">
        <div className="brand"><div className="brand-mark">M</div><div><strong>monk-e</strong><span>shared campaign intelligence</span></div></div>
        <div className="viewer-title"><span>{data.brand}</span><strong>{active.meta?.campaign}</strong></div>
        <Pill>READ ONLY</Pill>
      </header>
      <main className="viewer-main">
        <div className="viewer-toolbar">
          <div><div className="eyebrow">Brand POC view</div><h1>{data.brand} campaign performance</h1><p>Interactive campaign reporting using the latest persisted public Instagram data available to the Monk-E workspace.</p></div>
          <div className="viewer-select"><FileSpreadsheet size={14} /><select value={active.records?.[0]?.campaignId || ''} onChange={e => setSelectedId(e.target.value)}>{campaigns.map(c => <option key={c.records?.[0]?.campaignId} value={c.records?.[0]?.campaignId}>{c.meta?.campaign}</option>)}</select></div>
        </div>

        <div className="metric-grid viewer-metrics">
          <Metric icon={Eye} label="Recorded reach" value={fmt(summary.reach)} sub="Campaign workbook" accent="violet" />
          <Metric icon={MessageCircle} label="Engagement" value={fmt(summary.liveCoverage ? summary.liveEngagement : summary.engagement)} sub={summary.liveCoverage ? `${summary.liveCoverage.toFixed(0)}% public-live coverage` : 'Workbook value until live sync'} accent="mint" />
          <Metric icon={Users} label="Followers" value={fmt(summary.followers)} sub="Campaign source" accent="blue" />
          <Metric icon={BarChart3} label="Live views" value={fmt(summary.liveViews)} sub="Persisted public metric" accent="orange" />
        </div>

        <CampaignSentimentPanel campaignId={active.records?.[0]?.campaignId} initialResult={active.campaignSentiment} readonly />

        <div className="grid-two">
          <div className="panel"><div className="eyebrow">Distribution</div><h2>Reach by content category</h2><div className="chart"><ResponsiveContainer width="100%" height={300}><BarChart data={categories}><CartesianGrid strokeDasharray="4 4" vertical={false} /><XAxis dataKey="name" tickLine={false} axisLine={false} /><YAxis tickFormatter={fmt} tickLine={false} axisLine={false} /><Tooltip formatter={(value) => fmt(value)} /><Bar dataKey="liveViews" name="Public views" radius={[8,8,0,0]} fill="#8b5cf6" /></BarChart></ResponsiveContainer></div></div>
          <div className="panel"><div className="eyebrow">Mix</div><h2>Content share</h2><div className="chart"><ResponsiveContainer width="100%" height={300}><PieChart><Pie data={categories} dataKey="liveViews" nameKey="name" innerRadius={65} outerRadius={100} paddingAngle={3}>{categories.map((item, i) => <Cell key={item.name} fill={palette[i % palette.length]} />)}</Pie><Tooltip formatter={(value) => fmt(value)} /></PieChart></ResponsiveContainer></div><div className="viewer-legend">{categories.map((item, i) => <span key={item.name}><i style={{ background: palette[i % palette.length] }} />{item.name}</span>)}</div></div>
        </div>

        <div className="panel"><div className="eyebrow">Top content</div><h2>Highest public-view posts</h2><div className="viewer-post-grid">{topPosts.map(post => <article className="viewer-post-card" key={post.id}><PostThumbnail post={post} /><div><strong>@{post.username}</strong><span>{fmt(post.liveViews)} public views • {fmt(post.liveEngagement || post.engagement)} engagement</span></div></article>)}</div></div>
        <div className="viewer-footer">Read-only shared view • {data.brand} • {campaigns.length} campaign{campaigns.length === 1 ? '' : 's'} available</div>
      </main>
    </div>
  )
}
