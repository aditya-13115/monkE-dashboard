import { Download, ExternalLink, Filter, Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Avatar, LiveBadge, PostThumbnail, SectionHeader } from '../../components/common/UI'
import { useLivePost, seedLivePost } from '../../hooks/useLivePost'
import { fmt, pct } from '../../lib/metrics'

export default function Posts({ campaign, focusedId }) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All')
  const [type, setType] = useState('All')
  const [sort, setSort] = useState('reach')
  const [selected, setSelected] = useState(focusedId || null)
  const [live, setLive] = useState({})
  const { fetchLivePost, busy, error } = useLivePost()

  useEffect(() => {
    if (focusedId) setSelected(focusedId)
  }, [focusedId])

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    const filtered = campaign.records.filter(row => {
      const okQ = !q || String(row.username).toLowerCase().includes(q)
      const okC = category === 'All' || row.category === category
      const okT = type === 'All' || row.postType === type
      return okQ && okC && okT
    })
    return [...filtered].sort((a, b) => Number(b[sort] || 0) - Number(a[sort] || 0))
  }, [campaign.records, query, category, type, sort])

  async function openRow(row) {
    setSelected(row.id)
    const cached = live[row.id] || (row.liveDataAvailable ? row : null)
    if (!cached) {
      try {
        const result = await fetchLivePost(row.id)
        seedLivePost(result)
        setLive(prev => ({ ...prev, [row.id]: result }))
      } catch {
        // The workbook detail remains usable even when Instagram is unavailable.
      }
    }
  }

  function exportCsv() {
    const header = ['username', 'category', 'postType', 'followers', 'reach', 'engagement', 'engagementRateReach', 'postLink']
    const lines = [header.join(','), ...rows.map(row => header.map(key => JSON.stringify(row[key] ?? '')).join(','))]
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'monke-campaign-posts.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const currentBase = rows.find(row => row.id === selected)
  const current = currentBase ? { ...currentBase, ...(live[selected] || {}) } : null

  return (
    <div className="page">
      <SectionHeader
        eyebrow="Post-level intelligence"
        title="Post Explorer"
        copy={`${rows.length} placements in the current filter. Workbook reach stays intact; public Instagram counters persist once synced.`}
        action={<button className="ghost-btn" onClick={exportCsv}><Download size={15} /> Export CSV</button>}
      />

      {error && <div className="error-banner">Live Instagram: {error}</div>}

      <div className="toolbar">
        <div className="searchbox"><Search size={15} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search creator username" /></div>
        <div className="selectbox"><Filter size={15} /><select value={category} onChange={e => setCategory(e.target.value)}><option>All</option>{campaign.categories.map(c => <option key={c.name}>{c.name}</option>)}</select></div>
        <div className="selectbox"><select value={type} onChange={e => setType(e.target.value)}><option>All</option><option>Reel</option><option>Post</option></select></div>
        <div className="selectbox"><select value={sort} onChange={e => setSort(e.target.value)}><option value="reach">Sort: Reach</option><option value="engagement">Sort: Engagement</option><option value="engagementRateReach">Sort: Eng. rate</option><option value="followers">Sort: Followers</option></select></div>
      </div>

      <div className="panel table-panel">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Creator</th><th>Category</th><th>Type</th><th>Followers</th><th>Reach</th><th>Engagement</th><th>ER / reach</th><th>Live</th></tr></thead>
            <tbody>
              {rows.map(row => {
                const merged = { ...row, ...(live[row.id] || {}) }
                const engagement = Number(merged.liveDataAvailable ? merged.liveEngagement : merged.engagement || 0)
                const er = Number(merged.liveDataAvailable ? merged.liveEngagementRateReach : merged.engagementRateReach || 0)
                return (
                  <tr key={row.id} className={selected === row.id ? 'active-row' : ''} onClick={() => openRow(row)}>
                    <td><div className="creator-cell"><Avatar username={row.username} /><div><strong>@{row.username}</strong><span>{row.postType}</span></div></div></td>
                    <td>{row.category}</td>
                    <td>{row.postType}</td>
                    <td>{fmt(row.followers)}</td>
                    <td className="num">{fmt(row.reach)}</td>
                    <td className="num">{fmt(engagement)}</td>
                    <td className="num">{pct(er)}</td>
                    <td>{merged.liveDataAvailable ? <LiveBadge cached /> : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {current && (
          <div className="detail-drawer">
            <div>
              <div className="eyebrow">Selected placement</div>
              <h3>@{current.username}</h3>
              <p>{current.category} • {current.postType} {current.liveDataAvailable ? '• persisted Instagram data available' : '• workbook metrics only'}</p>
            </div>
            <button className="icon-btn" onClick={() => setSelected(null)}><X size={16} /></button>
            <div className="detail-metrics">
              <div><span>Reach</span><strong>{fmt(current.reach)}</strong></div>
              <div><span>{current.liveDataAvailable ? 'Live engagement' : 'Engagement'}</span><strong>{fmt(current.liveDataAvailable ? current.liveEngagement : current.engagement)}</strong></div>
              <div><span>ER / reach</span><strong>{pct(current.liveDataAvailable ? current.liveEngagementRateReach : current.engagementRateReach)}</strong></div>
              <div><span>{current.liveDataAvailable ? 'Views' : 'Followers'}</span><strong>{fmt(current.liveDataAvailable ? current.liveViews : current.followers)}</strong></div>
            </div>
            <div className="drawer-actions">
              {busy && <span className="muted">Syncing Instagram…</span>}
              <a className="primary-btn" href={current.postLink} target="_blank" rel="noreferrer">Open Instagram post <ExternalLink size={14} /></a>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
