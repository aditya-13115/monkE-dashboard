import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, BarChart3, Bot, ChevronDown, CircleGauge, Download,
  ExternalLink, FileSpreadsheet, Filter, Instagram, LayoutDashboard,
  MessageCircle, Search, Sparkles, Target, TrendingUp, Users,
  WandSparkles, X, CheckCircle2
} from 'lucide-react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart,
  Line, Pie, PieChart, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis
} from 'recharts'
import './styles.css'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const navItems = [
  ['overview', 'Overview', LayoutDashboard],
  ['posts', 'Post Explorer', Instagram],
  ['creators', 'Creator Analytics', Users],
  ['categories', 'Category Insights', BarChart3],
  ['sentiment', 'AI Sentiment', Bot],
  ['insights', 'Campaign Insights', Sparkles],
]

const fmt = n => {
  const v = Number(n || 0)
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)}B`
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(v >= 10e6 ? 1 : 2)}M`
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(v >= 100e3 ? 0 : 1)}K`
  return new Intl.NumberFormat('en-IN').format(v)
}

const pct = n => `${Number(n || 0).toFixed(2)}%`

const initials = name => name.replace(/^@/, '').slice(0, 2).toUpperCase()

function Metric({ icon: Icon, label, value, sub, accent }) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <div className={`metric-icon ${accent || ''}`}><Icon size={16}/></div>
        <span>{label}</span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-sub">{sub}</div>
    </div>
  )
}

function SectionHeader({ eyebrow, title, copy, action }) {
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

function Pill({ children, tone='' }) {
  return <span className={`pill ${tone}`}>{children}</span>
}

function Overview({ campaign, onGo }) {
  const { summary, records, categories } = campaign
  const categoryBar = categories.map(c => ({ name: c.name, reach: c.reach, engagement: c.engagement }))
  const topPosts = [...records].sort((a,b)=>b.reach-a.reach).slice(0,8)

  return (
    <div className="page">
      <SectionHeader
        eyebrow="Campaign command center"
        title={campaign.meta.campaign}
        copy={`${campaign.meta.platform} creator campaign • ${campaign.meta.date} • ${summary.totalPosts} deliverables`}
        action={<button className="ghost-btn" onClick={()=>onGo('posts')}><FileSpreadsheet size={15}/> Explore posts</button>}
      />

      <div className="metric-grid">
        <Metric icon={Target} label="Total reach" value={fmt(summary.totalReach)} sub="Across tracked posts" accent="violet"/>
        <Metric icon={Activity} label="Engagement" value={fmt(summary.totalEngagement)} sub={`${pct(summary.engagementRateReach)} of reach`} accent="mint"/>
        <Metric icon={Users} label="Creator audience" value={fmt(summary.totalFollowers)} sub="Combined follower base" accent="blue"/>
        <Metric icon={CircleGauge} label="Avg reach / post" value={fmt(summary.avgReachPerPost)} sub={`${summary.totalPosts} posts tracked`} accent="orange"/>
        <Metric icon={TrendingUp} label="Reach efficiency" value={pct(summary.engagementRateReach)} sub="Engagement ÷ reach" accent="pink"/>
      </div>

      <div className="grid-two">
        <div className="panel">
          <SectionHeader eyebrow="Distribution" title="Reach & engagement by creator category" copy="Compare where campaign delivery is concentrated."/>
          <div className="chart"><ResponsiveContainer width="100%" height={310}>
            <BarChart data={categoryBar} margin={{top:10,right:10,left:0,bottom:10}}>
              <CartesianGrid strokeDasharray="4 4" vertical={false}/>
              <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{fontSize:11}}/>
              <YAxis tickFormatter={fmt} tickLine={false} axisLine={false} width={55}/>
              <Tooltip formatter={(v,n)=>[fmt(v), n === 'reach' ? 'Reach' : 'Engagement']}/>
              <Bar dataKey="reach" name="Reach" radius={[7,7,0,0]} fill="#8b5cf6"/>
              <Bar dataKey="engagement" name="Engagement" radius={[7,7,0,0]} fill="#10b981"/>
            </BarChart>
          </ResponsiveContainer></div>
        </div>

        <div className="panel">
          <SectionHeader eyebrow="Top content" title="Posts pulling the most reach" copy="Fast view of the campaign's highest-reach placements."/>
          <div className="rank-list">
            {topPosts.map((p, i) => (
              <button className="rank-row" key={p.id} onClick={()=>onGo('posts', p.id)}>
                <div className="rank-num">{String(i+1).padStart(2,'0')}</div>
                <div className="avatar">{initials(p.username)}</div>
                <div className="rank-main">
                  <strong>@{p.username}</strong>
                  <span>{p.category} • {p.postType}</span>
                </div>
                <div className="rank-value">{fmt(p.reach)}<small> reach</small></div>
                <ExternalLink size={14}/>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid-three">
        <div className="panel compact">
          <div className="mini-title">Category share of reach</div>
          <div className="chart small"><ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={categories} dataKey="reach" nameKey="name" innerRadius={56} outerRadius={82} paddingAngle={2}>
                {categories.map((_, i)=><Cell key={i} fill={['#8b5cf6','#0ea5e9','#10b981','#f59e0b','#f43f5e'][i%5]}/>)}
              </Pie>
              <Tooltip formatter={v=>fmt(v)}/>
            </PieChart>
          </ResponsiveContainer></div>
          <div className="legend-grid">{categories.map((c,i)=><div key={c.name}><span className="legend-dot" style={{background:['#8b5cf6','#0ea5e9','#10b981','#f59e0b','#f43f5e'][i%5]}}/>{c.name}</div>)}</div>
        </div>

        <div className="panel compact">
          <div className="mini-title">Content mix</div>
          <div className="donut-row">
            {['Reel','Post'].map(type=>{
              const rows=records.filter(r=>r.postType===type)
              const share=records.length ? rows.length/records.length*100 : 0
              return <div className="donut-stat" key={type}>
                <div className="donut" style={{'--p':`${share*3.6}deg`}}><strong>{Math.round(share)}%</strong></div>
                <span>{type}</span><small>{rows.length} deliverables</small>
              </div>
            })}
          </div>
          <div className="insight-chip"><WandSparkles size={15}/> Reels dominate tracked placements; keep post format visible for efficiency comparisons.</div>
        </div>

        <div className="panel compact">
          <div className="mini-title">Campaign snapshot</div>
          <div className="snapshot-list">
            <div><span>Creators</span><strong>{summary.totalCreators}</strong></div>
            <div><span>Deliverables</span><strong>{summary.totalPosts}</strong></div>
            <div><span>Expected views</span><strong>{campaign.meta.expectedViews}</strong></div>
            <div><span>Categories</span><strong>{categories.length}</strong></div>
            <div><span>Platform</span><strong>{campaign.meta.platform}</strong></div>
          </div>
        </div>
      </div>
    </div>
  )
}

function Posts({ campaign, focusedId }) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All')
  const [type, setType] = useState('All')
  const [sort, setSort] = useState('reach')
  const [selected, setSelected] = useState(focusedId || null)

  useEffect(()=>{ if(focusedId) setSelected(focusedId) }, [focusedId])

  const rows = useMemo(()=>{
    let out=campaign.records.filter(r=>{
      const q=query.toLowerCase()
      const okQ=!q || r.username.toLowerCase().includes(q)
      const okC=category==='All' || r.category===category
      const okT=type==='All' || r.postType===type
      return okQ && okC && okT
    })
    out=[...out].sort((a,b)=>(b[sort]-a[sort]))
    return out
  },[campaign.records,query,category,type,sort])

  const current=rows.find(r=>r.id===selected)

  function exportCsv() {
    const header = ['username','category','postType','followers','reach','engagement','engagementRateReach','postLink']
    const lines=[header.join(','), ...rows.map(r=>header.map(k=>JSON.stringify(r[k] ?? '')).join(','))]
    const blob=new Blob([lines.join('\\n')],{type:'text/csv'})
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='monke-campaign-posts.csv'; a.click(); URL.revokeObjectURL(a.href)
  }

  return (
    <div className="page">
      <SectionHeader eyebrow="Post-level intelligence" title="Post Explorer" copy={`${rows.length} placements in current filter`}>
        <button className="ghost-btn" onClick={exportCsv}><Download size={15}/> Export CSV</button>
      </SectionHeader>

      <div className="toolbar">
        <div className="searchbox"><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search creator username"/></div>
        <div className="selectbox"><Filter size={15}/><select value={category} onChange={e=>setCategory(e.target.value)}><option>All</option>{campaign.categories.map(c=><option key={c.name}>{c.name}</option>)}</select></div>
        <div className="selectbox"><select value={type} onChange={e=>setType(e.target.value)}><option>All</option><option>Reel</option><option>Post</option></select></div>
        <div className="selectbox"><select value={sort} onChange={e=>setSort(e.target.value)}><option value="reach">Sort: Reach</option><option value="engagement">Sort: Engagement</option><option value="engagementRateReach">Sort: Eng. rate</option><option value="followers">Sort: Followers</option></select></div>
      </div>

      <div className="panel table-panel">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Creator</th><th>Category</th><th>Type</th><th>Followers</th><th>Reach</th><th>Engagement</th><th>ER / reach</th><th></th></tr></thead>
            <tbody>
            {rows.map(r=>(
              <tr key={r.id} className={selected===r.id?'active-row':''} onClick={()=>setSelected(r.id)}>
                <td><div className="creator-cell"><div className="avatar">{initials(r.username)}</div><div><strong>@{r.username}</strong><span>{r.postLink ? 'Instagram placement' : ''}</span></div></div></td>
                <td><Pill>{r.category}</Pill></td><td><span className="type-dot"/>{r.postType}</td>
                <td>{fmt(r.followers)}</td><td className="num">{fmt(r.reach)}</td><td className="num">{fmt(r.engagement)}</td><td className="num">{pct(r.engagementRateReach)}</td>
                <td><ExternalLink size={14}/></td>
              </tr>
            ))}
            </tbody>
          </table>
        </div>
        {current && <div className="detail-drawer">
          <div>
            <div className="eyebrow">Selected placement</div>
            <h3>@{current.username}</h3>
            <p>{current.category} • {current.postType}</p>
          </div>
          <button className="icon-btn" onClick={()=>setSelected(null)}><X size={16}/></button>
          <div className="detail-metrics">
            <div><span>Reach</span><strong>{fmt(current.reach)}</strong></div>
            <div><span>Engagement</span><strong>{fmt(current.engagement)}</strong></div>
            <div><span>ER / reach</span><strong>{pct(current.engagementRateReach)}</strong></div>
            <div><span>Followers</span><strong>{fmt(current.followers)}</strong></div>
          </div>
          <a className="primary-btn" href={current.postLink} target="_blank" rel="noreferrer">Open Instagram post <ExternalLink size={14}/></a>
        </div>}
      </div>
    </div>
  )
}

function Creators({ campaign }) {
  const [sort,setSort]=useState('reach')
  const rows=[...campaign.records].sort((a,b)=>b[sort]-a[sort]).slice(0,25)
  const scatter = campaign.records.map(r=>({x:r.followers,y:r.reach,z:Math.max(12,r.engagement),name:r.username}))

  return <div className="page">
    <SectionHeader eyebrow="Creator intelligence" title="Creator Analytics" copy="Understand scale, delivery and efficiency together."/>
    <div className="grid-two">
      <div className="panel">
        <SectionHeader eyebrow="Audience → outcome" title="Follower base vs reach"/>
        <div className="chart"><ResponsiveContainer width="100%" height={340}>
          <ScatterChart margin={{top:10,right:15,bottom:10,left:5}}>
            <CartesianGrid strokeDasharray="4 4"/>
            <XAxis type="number" dataKey="x" name="Followers" tickFormatter={fmt} tickLine={false}/>
            <YAxis type="number" dataKey="y" name="Reach" tickFormatter={fmt} tickLine={false}/>
            <Tooltip cursor={{strokeDasharray:'3 3'}} formatter={(v,n)=>[fmt(v), n]}/>
            <Scatter data={scatter} fill="#8b5cf6"/>
          </ScatterChart>
        </ResponsiveContainer></div>
      </div>
      <div className="panel">
        <SectionHeader eyebrow="Performance table" title="Top creator placements" action={<div className="selectbox"><select value={sort} onChange={e=>setSort(e.target.value)}><option value="reach">Reach</option><option value="engagement">Engagement</option><option value="engagementRateReach">Engagement rate</option></select></div>}/>
        <div className="rank-list scroll">
        {rows.map((r,i)=><div className="rank-row" key={r.id}>
          <div className="rank-num">{String(i+1).padStart(2,'0')}</div><div className="avatar">{initials(r.username)}</div>
          <div className="rank-main"><strong>@{r.username}</strong><span>{r.category}</span></div>
          <div className="stacked-value"><strong>{sort==='reach'?fmt(r.reach):sort==='engagement'?fmt(r.engagement):pct(r.engagementRateReach)}</strong><span>{sort==='reach'?'reach':sort==='engagement'?'engagement':'ER'}</span></div>
        </div>)}
        </div>
      </div>
    </div>
  </div>
}

function Categories({ campaign }) {
  const rows=campaign.categories.map(c=>({...c, share:c.reach/campaign.summary.totalReach*100}))
  return <div className="page">
    <SectionHeader eyebrow="Category intelligence" title="Category Insights" copy="See where delivery is concentrated and which creator pools contribute to it."/>
    <div className="grid-three">
      {rows.map((c,i)=><div className="panel category-card" key={c.name}>
        <div className="category-top"><Pill>{c.name}</Pill><span>{c.creators} creators</span></div>
        <div className="category-hero">{fmt(c.reach)}<small>reach</small></div>
        <div className="progress"><span style={{width:`${Math.min(100,c.share)}%`}}/></div>
        <div className="category-stats">
          <div><span>Engagement</span><strong>{fmt(c.engagement)}</strong></div>
          <div><span>ER / reach</span><strong>{pct(c.engagementRate)}</strong></div>
          <div><span>Followers</span><strong>{fmt(c.followers)}</strong></div>
          <div><span>Reach share</span><strong>{c.share.toFixed(1)}%</strong></div>
        </div>
      </div>)}
    </div>
    <div className="panel">
      <SectionHeader eyebrow="Efficiency" title="Reach vs engagement by category"/>
      <div className="chart"><ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={rows} margin={{top:10,right:10,left:0,bottom:10}}>
          <CartesianGrid strokeDasharray="4 4" vertical={false}/>
          <XAxis dataKey="name" tickLine={false} axisLine={false}/>
          <YAxis yAxisId="left" tickFormatter={fmt} tickLine={false} axisLine={false}/>
          <YAxis yAxisId="right" orientation="right" tickFormatter={v=>`${v}%`} tickLine={false} axisLine={false}/>
          <Tooltip formatter={(v,n)=>[n==='engagementRate'?`${v}%`:fmt(v),n]}/>
          <Bar yAxisId="left" dataKey="reach" radius={[8,8,0,0]} fill="#8b5cf6" name="Reach"/>
          <Line yAxisId="right" type="monotone" dataKey="engagementRate" stroke="#10b981" strokeWidth={3} dot={{r:4}} name="ER"/>
        </ComposedChart>
      </ResponsiveContainer></div>
    </div>
  </div>
}

function thumbnailFor(post) {
  if (post?.thumbnailUrl) return post.thumbnailUrl
  if (!post?.postLink) return ''
  return ''
}

function LiveBadge({ source = 'Instagram' }) {
  return (
    <span className="live-badge">
      <span className="live-dot" />
      {source}
    </span>
  )
}

function PostThumbnail({ post, live }) {
  const [failed, setFailed] = useState(false)
  const src = thumbnailFor(live || post)

  useEffect(() => setFailed(false), [src])

  return (
    <div className="sentiment-thumb">
      {!failed && src ? (
        <img
          src={src}
          alt={`@${post.username} ${post.postType}`}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : null}
      {(failed || !src) && (
        <div className="sentiment-thumb-fallback">
          <div className="instagram-glyph"><Instagram size={22}/></div>
          <strong>@{post.username}</strong>
          <span>{post.postType}</span>
        </div>
      )}
      <div className="sentiment-thumb-overlay">
        <Instagram size={13}/>
        <span>{post.postType}</span>
      </div>
    </div>
  )
}

function LivePostCard({ post, live, onLive, onAnalyze, busy, selected }) {
  const ref = useRef(null)
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(Boolean(live?.liveDataAvailable))
  const [localError, setLocalError] = useState('')

  useEffect(() => {
    if (live?.liveDataAvailable) {
      setLoaded(true)
      return
    }

    const node = ref.current
    if (!node || typeof IntersectionObserver === 'undefined') return

    let cancelled = false
    const observer = new IntersectionObserver(async entries => {
      if (!entries.some(entry => entry.isIntersecting)) return
      observer.disconnect()
      setLoading(true)
      setLocalError('')
      try {
        const res = await fetch(`${API}/api/posts/${post.id}/live`)
        const data = await res.json()
        if (!res.ok) throw new Error(data.detail || 'Live Instagram fetch failed')
        if (!cancelled) {
          onLive(post.id, data.post)
          setLoaded(true)
        }
      } catch (error) {
        if (!cancelled) setLocalError(error.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, { rootMargin: '500px' })

    observer.observe(node)

    return () => {
      cancelled = true
      observer.disconnect()
    }
  }, [post.id, live?.liveDataAvailable, onLive])

  const merged = live || post
  const reach = Number(merged.reach || post.reach || 0)
  const engagement = Number(
    merged.liveEngagement ?? merged.engagement ?? post.engagement ?? 0
  )
  const likes = Number(merged.liveLikes ?? 0)
  const comments = Number(merged.liveComments ?? 0)
  const views = Number(merged.liveViews ?? 0)
  const er = reach > 0 ? (engagement / reach) * 100 : Number(merged.engagementRateReach || 0)

  return (
    <button
      ref={ref}
      className={`sentiment-post-card ${selected ? 'selected' : ''}`}
      onClick={() => onAnalyze(merged)}
      disabled={busy && selected}
    >
      <PostThumbnail post={post} live={merged} />

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
          {loaded ? <LiveBadge /> : loading ? <span>Syncing Instagram…</span> : <span>Workbook metrics</span>}
          <span>{pct(er)} ER</span>
        </div>

        {localError && <small className="live-card-error">Live: {localError}</small>}
      </div>

      {busy && selected && (
        <div className="sentiment-card-loading">
          <div className="loader mini"/> Analyzing comments
        </div>
      )}
    </button>
  )
}

function Sentiment({ campaign, sentiment, setSentiment, onLive }) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All')
  const [type, setType] = useState('All')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [selectedPost, setSelectedPost] = useState(null)

  const posts = useMemo(() => {
    const q = query.trim().toLowerCase()
    return campaign.records.filter(post => {
      const username = String(post.username || '').toLowerCase()
      const okQ = !q || username.includes(q)
      const okC = category === 'All' || post.category === category
      const okT = type === 'All' || post.postType === type
      return okQ && okC && okT
    })
  }, [campaign.records, query, category, type])

  async function analyzePost(post) {
    if (!post || busy) return

    setSelectedPost(post)
    setBusy(true)
    setError('')
    setSentiment(null)

    try {
      // Refresh visible post metrics first. This also gives the sentiment page
      // the best available thumbnail.
      let latestPost = post
      try {
        const liveRes = await fetch(`${API}/api/posts/${post.id}/live`)
        const liveData = await liveRes.json()
        if (liveRes.ok && liveData.post) {
          latestPost = liveData.post
          onLive(post.id, liveData.post)
          setSelectedPost(liveData.post)
        }
      } catch {
        // Sentiment still proceeds; Excel values remain available as fallback.
      }

      const res = await fetch(`${API}/api/sentiment/post/${post.id}`, {
        method: 'POST',
      })
      const data = await res.json()

      if (!res.ok) {
        throw new Error(data.detail || 'Sentiment analysis failed')
      }

      const safe = {
        ...data,
        post: data.post || latestPost,
        analysis: data.analysis || { summary: {}, topics: [], results: [], sample: {} },
      }

      setSentiment(safe)
      setSelectedPost({ ...latestPost, ...(data.post || {}) })

      setTimeout(() => {
        document.getElementById('sentiment-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 80)
    } catch (e) {
      setError(e?.message || 'Sentiment analysis failed')
    } finally {
      setBusy(false)
    }
  }

  const analysis = sentiment?.analysis
  const summary = analysis?.summary || {}
  const topics = Array.isArray(analysis?.topics) ? analysis.topics : []
  const results = Array.isArray(analysis?.results) ? analysis.results : []
  const sample = analysis?.sample || {}
  const pie = analysis ? [
    { name: 'Positive', value: Number(summary.positive || 0) },
    { name: 'Neutral', value: Number(summary.neutral || 0) },
    { name: 'Negative', value: Number(summary.negative || 0) },
  ] : []
  const maxTopic = Math.max(1, ...topics.map(item => Number(item.count || 0)))

  return (
    <div className="page">
      <SectionHeader
        eyebrow="AI audience voice"
        title="Comment Sentiment"
        copy="Select a campaign post. Monk-E opens the exact Instagram POST LINK from the Excel, pulls the available comments, samples them, and sends them to Groq."
        action={selectedPost && (
          <a className="ghost-btn" href={selectedPost.postLink} target="_blank" rel="noreferrer">
            Open selected post <ExternalLink size={14}/>
          </a>
        )}
      />

      <div className="info-banner">
        <Bot size={18}/>
        <div>
          <strong>Post-level AI analysis</strong>
          <span>Live public post metrics are fetched on demand. Comment analysis uses up to 100 comments from Instagram, weighted toward higher-liked comments, then Groq classifies sentiment, topics and emotions.</span>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {selectedPost && analysis && (
        <div id="sentiment-results" className="sentiment-results-anchor">
          <div className="selected-post-banner result-banner">
            <PostThumbnail post={selectedPost} live={selectedPost}/>
            <div>
              <div className="eyebrow">AI analysis ready</div>
              <h3>@{selectedPost.username}</h3>
              <p>{selectedPost.category} • {selectedPost.postType} • {fmt(sentiment.commentsAvailable)} comments available</p>
            </div>
            <div className="selected-post-actions">
              <Pill>{sample.selected || results.length} sampled</Pill>
              <Pill>{sample.likedShare || 0}% liked-comment pool</Pill>
              <Pill tone="positive"><CheckCircle2 size={11}/> Groq complete</Pill>
            </div>
          </div>

          <div className="metric-grid">
            <Metric icon={MessageCircle} label="Sampled comments" value={fmt(sample.selected || results.length)} sub={`${sample.likedShare || 0}% from liked pool`} accent="violet"/>
            <Metric icon={TrendingUp} label="Positive" value={`${Number(summary.positivePct || 0).toFixed(1)}%`} sub={`${summary.positive || 0} comments`} accent="mint"/>
            <Metric icon={CircleGauge} label="Neutral" value={`${Number(summary.neutralPct || 0).toFixed(1)}%`} sub={`${summary.neutral || 0} comments`} accent="blue"/>
            <Metric icon={Target} label="Negative" value={`${Number(summary.negativePct || 0).toFixed(1)}%`} sub={`${summary.negative || 0} comments`} accent="pink"/>
            <Metric icon={Bot} label="Model" value="GPT-OSS" sub={analysis.model || 'Groq'} accent="orange"/>
          </div>

          <div className="grid-two">
            <div className="panel">
              <SectionHeader eyebrow="Tone mix" title="Audience sentiment"/>
              <div className="chart"><ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={pie} dataKey="value" nameKey="name" innerRadius={72} outerRadius={104} paddingAngle={3}>
                    <Cell fill="#10b981"/><Cell fill="#94a3b8"/><Cell fill="#f43f5e"/>
                  </Pie>
                  <Tooltip/>
                </PieChart>
              </ResponsiveContainer></div>
              <div className="sentiment-legend">
                <span><i className="mint"/>{Number(summary.positivePct || 0).toFixed(1)}% positive</span>
                <span><i className="slate"/>{Number(summary.neutralPct || 0).toFixed(1)}% neutral</span>
                <span><i className="rose"/>{Number(summary.negativePct || 0).toFixed(1)}% negative</span>
              </div>
            </div>

            <div className="panel">
              <SectionHeader eyebrow="Conversation themes" title="What people are talking about"/>
              {topics.length ? (
                <div className="topic-list">
                  {topics.map(t => (
                    <div className="topic-row" key={t.topic}>
                      <span>{t.topic}</span>
                      <div className="topic-track"><b style={{width:`${Math.min(100, Number(t.count || 0) / maxTopic * 100)}%`}}/></div>
                      <strong>{t.count}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="muted">No topic results were returned.</div>
              )}
            </div>
          </div>

          <div className="panel">
            <SectionHeader eyebrow="Comment review" title="Sampled comments" copy={`Showing the first 20 of ${results.length} analyzed comments.`}/>
            <div className="comments">
              {results.slice(0,20).map((r, index) => (
                <div className="comment-row" key={`${r.id || index}-${r.username || ''}`}>
                  <div className="avatar">{initials(r.username || 'IG')}</div>
                  <div className="comment-main">
                    <div><strong>{r.username ? `@${r.username}` : 'Instagram user'}</strong><span>♥ {fmt(r.likes || 0)}</span></div>
                    <p>{r.comment}</p>
                    <small>{r.topic || 'other'} • {r.emotion || 'neutral'} • {Math.round(Number(r.confidence || 0) * 100)}% confidence</small>
                  </div>
                  <Pill tone={r.sentiment}>{r.sentiment}</Pill>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="toolbar">
        <div className="searchbox">
          <Search size={15}/>
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search creator username"/>
        </div>
        <div className="selectbox">
          <Filter size={15}/>
          <select value={category} onChange={e => setCategory(e.target.value)}>
            <option>All</option>
            {campaign.categories.map(c => <option key={c.name}>{c.name}</option>)}
          </select>
        </div>
        <div className="selectbox">
          <select value={type} onChange={e => setType(e.target.value)}>
            <option>All</option><option>Reel</option><option>Post</option>
          </select>
        </div>
        <div className="sentiment-post-count">
          {posts.length} posts available
        </div>
      </div>

      <div className="sentiment-post-grid">
        {posts.map(post => (
          <LivePostCard
            key={post.id}
            post={post}
            live={post.liveDataAvailable ? post : null}
            onLive={onLive}
            onAnalyze={analyzePost}
            busy={busy}
            selected={selectedPost?.id === post.id}
          />
        ))}
      </div>

      {!selectedPost && (
        <div className="empty-panel sentiment-empty">
          <div className="empty-icon"><MessageCircle size={28}/></div>
          <h3>Select a post to analyze</h3>
          <p>Each card uses the exact POST LINK from the campaign workbook. Thumbnails and public Instagram metrics are loaded lazily as cards enter the viewport.</p>
        </div>
      )}
    </div>
  )
}

function Insights({ campaign }) {
  const {records,summary,categories}=campaign
  const topReach=[...records].sort((a,b)=>b.reach-a.reach)[0]
  const topER=[...records].sort((a,b)=>b.engagementRateReach-a.engagementRateReach)[0]
  const topEng=[...records].sort((a,b)=>b.engagement-a.engagement)[0]
  const top10Reach=[...records].sort((a,b)=>b.reach-a.reach).slice(0,10).reduce((s,r)=>s+r.reach,0)
  const concentration=top10Reach/summary.totalReach*100
  return <div className="page">
    <SectionHeader eyebrow="Decision support" title="Campaign Insights" copy="Concise operational signals derived directly from the uploaded performance sheet."/>
    <div className="grid-three">
      <div className="insight-card"><div className="insight-label">Scale signal</div><h3>@{topReach.username}</h3><p>Highest recorded reach at <strong>{fmt(topReach.reach)}</strong>.</p><span>{topReach.category} • {topReach.postType}</span></div>
      <div className="insight-card"><div className="insight-label">Interaction signal</div><h3>@{topER.username}</h3><p>Highest engagement-to-reach rate at <strong>{pct(topER.engagementRateReach)}</strong>.</p><span>{fmt(topER.engagement)} engagements</span></div>
      <div className="insight-card"><div className="insight-label">Engagement volume</div><h3>@{topEng.username}</h3><p>Highest total engagement at <strong>{fmt(topEng.engagement)}</strong>.</p><span>{fmt(topEng.reach)} reach</span></div>
    </div>
    <div className="grid-two">
      <div className="panel">
        <SectionHeader eyebrow="Concentration" title="How concentrated is reach?"/>
        <div className="big-stat">{concentration.toFixed(1)}%<small>of total reach comes from the top 10 placements</small></div>
        <div className="progress"><span style={{width:`${Math.min(100,concentration)}%`}}/></div>
        <p className="muted">Use this as a concentration diagnostic when deciding how much performance depends on a small number of creator placements.</p>
      </div>
      <div className="panel">
        <SectionHeader eyebrow="Operational checklist" title="Next review areas"/>
        <div className="check-list">
          <div><span className="check">01</span><strong>Audit low-reach placements</strong><p>Open Post Explorer and review category + creator patterns.</p></div>
          <div><span className="check">02</span><strong>Compare efficiency, not just scale</strong><p>Creator Analytics pairs follower base with actual reach and engagement.</p></div>
          <div><span className="check">03</span><strong>Read audience voice</strong><p>Select a post in AI Sentiment to analyze its audience voice with Groq.</p></div>
        </div>
      </div>
    </div>
  </div>
}

function App() {
  const [active,setActive]=useState('overview')
  const [campaign,setCampaign]=useState(null)
  const [focusedId,setFocusedId]=useState(null)
  const [sentiment,setSentiment]=useState(null)

  useEffect(()=>{
    fetch(`${API}/api/campaign`)
      .then(r=>r.ok?r.json():Promise.reject(new Error('Campaign API unavailable')))
      .then(setCampaign)
      .catch(()=>fetch('/campaign.json')
        .then(r=>r.json())
        .then(data=>{
          const totalReach=data.records.reduce((s,r)=>s+r.reach,0)
          const totalEngagement=data.records.reduce((s,r)=>s+r.engagement,0)
          const totalFollowers=data.records.reduce((s,r)=>s+r.followers,0)
          const cats=[...new Set(data.records.map(r=>r.category))].map(name=>{
            const rs=data.records.filter(r=>r.category===name)
            const reach=rs.reduce((s,r)=>s+r.reach,0)
            const engagement=rs.reduce((s,r)=>s+r.engagement,0)
            return {name,creators:rs.length,deliverables:rs.length,followers:rs.reduce((s,r)=>s+r.followers,0),reach,engagement,engagementRate:reach?engagement/reach*100:0}
          })
          setCampaign({
            meta:data.meta,
            summary:{
              totalCreators:data.records.length,
              totalPosts:data.records.length,
              totalFollowers,
              totalReach,
              totalEngagement,
              engagementRateReach:totalReach?totalEngagement/totalReach*100:0,
              avgReachPerPost:data.records.length?totalReach/data.records.length:0
            },
            categories:cats,
            records:data.records
          })
        }))
      .catch(console.error)
  },[])

  function handleLivePost(id, livePost) {
    if (!livePost) return

    setCampaign(prev => {
      if (!prev) return prev

      return {
        ...prev,
        records: prev.records.map(record =>
          record.id === id
            ? { ...record, ...livePost }
            : record
        ),
      }
    })
  }

  if(!campaign) return <div className="loading"><div className="loader"/><span>Loading campaign intelligence…</span></div>

  const go=(page,id)=>{
    setActive(page)
    if(id) setFocusedId(id)
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">M</div><div><strong>monk-e</strong><span>campaign intelligence</span></div></div>
      <div className="campaign-switch"><span>Active campaign</span><strong>{campaign.meta.campaign}</strong><small>{campaign.meta.platform} · {campaign.meta.date}</small></div>
      <nav>{navItems.map(([key,label,Icon])=><button key={key} className={active===key?'active':''} onClick={()=>go(key)}><Icon size={17}/><span>{label}</span>{key==='sentiment'&&<Pill>AI</Pill>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="status-dot"/><div><strong>Campaign data connected</strong><span>{campaign.summary.totalPosts} placements loaded</span></div></div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div><span className="eyebrow">Monk-E / Campaign dashboard</span><h1>{navItems.find(x=>x[0]===active)?.[1]}</h1></div>
        <div className="top-actions"><div className="live-pill"><span className="status-dot"/>Instagram sync on demand</div><button className="icon-btn"><ChevronDown size={16}/></button></div>
      </header>
      {active==='overview' && <Overview campaign={campaign} onGo={go}/>} 
      {active==='posts' && <Posts campaign={campaign} focusedId={focusedId}/>} 
      {active==='creators' && <Creators campaign={campaign}/>} 
      {active==='categories' && <Categories campaign={campaign}/>} 
      {active==='sentiment' && <Sentiment campaign={campaign} sentiment={sentiment} setSentiment={setSentiment} onLive={handleLivePost}/>} 
      {active==='insights' && <Insights campaign={campaign}/>} 
    </main>
  </div>
}

export default App
