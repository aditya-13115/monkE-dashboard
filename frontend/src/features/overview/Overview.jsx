import { Activity, CircleGauge, Target, TrendingUp, Users } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Metric, Pill, SectionHeader, Avatar } from '../../components/common/UI'
import EmptyChart from '../../components/charts/EmptyChart'
import { fmt, pct, publicEngagement } from '../../lib/metrics'

const colors = ['#8b5cf6', '#0ea5e9', '#10b981', '#f59e0b', '#f43f5e']

export default function Overview({ campaign, onGo }) {
  const { summary, records, categories } = campaign
  const liveCount = Number(summary.livePostsSynced || 0)
  const liveEngagement = Number(summary.liveEngagement || 0)
  const categoryBar = categories.map((c, index) => ({
    name: c.name,
    reach: c.reach,
    liveEngagement: c.livePosts ? c.liveEngagement : 0,
    sheetEngagement: c.engagement,
    livePosts: c.livePosts || 0,
    fill: colors[index % colors.length],
  }))
  const topPosts = [...records].sort((a, b) => b.reach - a.reach).slice(0, 8)

  return (
    <div className="page">
      <SectionHeader
        eyebrow="Campaign command center"
        title={campaign.meta.campaign}
        copy={`${campaign.meta.platform} creator campaign • ${campaign.meta.date} • ${summary.totalPosts} deliverables`}
        action={<button className="ghost-btn" onClick={() => onGo('posts')}><span>Explore posts</span></button>}
      />

      <div className="data-source-strip">
        <span><b>{liveCount}/{summary.totalPosts}</b> placements have persisted public Instagram data.</span>
        <span>Reach and follower base remain workbook metrics because Instagram does not reliably expose owner-only reach publicly.</span>
      </div>

      <div className="metric-grid">
        <Metric icon={Target} label="Total reach" value={fmt(summary.totalReach)} sub="Campaign workbook" accent="violet" />
        <Metric icon={Activity} label="Live public engagement" value={fmt(liveEngagement)} sub={`${liveCount} synced posts`} accent="mint" />
        <Metric icon={Users} label="Creator audience" value={fmt(summary.totalFollowers)} sub="Campaign workbook" accent="blue" />
        <Metric icon={CircleGauge} label="Avg reach / post" value={fmt(summary.avgReachPerPost)} sub="Workbook reach" accent="orange" />
        <Metric icon={TrendingUp} label="Live ER / reach" value={pct(summary.liveEngagementRateOfReach)} sub="Public engagement ÷ workbook reach" accent="pink" />
      </div>

      <div className="grid-two">
        <div className="panel">
          <SectionHeader eyebrow="Live + recorded performance" title="Reach & public engagement by category" copy="Reach is from the campaign sheet; engagement switches to live public Instagram values for synced placements." />
          {liveCount ? (
            <div className="chart"><ResponsiveContainer width="100%" height={310}>
              <BarChart data={categoryBar} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
                <CartesianGrid strokeDasharray="4 4" vertical={false} />
                <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={fmt} tickLine={false} axisLine={false} width={55} />
                <Tooltip formatter={(value, name) => [fmt(value), name === 'reach' ? 'Reach' : 'Live public engagement']} />
                <Bar dataKey="reach" name="Reach" radius={[7, 7, 0, 0]} fill="#8b5cf6" />
                <Bar dataKey="liveEngagement" name="Live public engagement" radius={[7, 7, 0, 0]} fill="#10b981" />
              </BarChart>
            </ResponsiveContainer></div>
          ) : <EmptyChart text="Open or sync a post to seed persistent live Instagram metrics for the charts." />}
        </div>

        <div className="panel">
          <SectionHeader eyebrow="Top content" title="Posts pulling the most recorded reach" copy="Reach is the workbook metric; use Post Explorer for live public counters on individual posts." />
          <div className="rank-list">
            {topPosts.map((p, i) => (
              <button className="rank-row" key={p.id} onClick={() => onGo('posts', p.id)}>
                <div className="rank-num">{String(i + 1).padStart(2, '0')}</div>
                <Avatar username={p.username} />
                <div className="rank-main">
                  <strong>@{p.username}</strong>
                  <span>{p.category} • {p.postType}{p.liveDataAvailable ? ' • live synced' : ''}</span>
                </div>
                <div className="rank-value">{fmt(p.reach)}<small> reach</small></div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid-three">
        <div className="panel compact">
          <div className="mini-title">Category share of recorded reach</div>
          <div className="chart small"><ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={categories} dataKey="reach" nameKey="name" innerRadius={56} outerRadius={82} paddingAngle={2}>
                {categories.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}
              </Pie>
              <Tooltip formatter={value => fmt(value)} />
            </PieChart>
          </ResponsiveContainer></div>
          <div className="legend-grid">{categories.map((c, i) => <div key={c.name}><span className="legend-dot" style={{ background: colors[i % colors.length] }} />{c.name}</div>)}</div>
        </div>

        <div className="panel compact">
          <div className="mini-title">Live public engagement coverage</div>
          <div className="big-stat">{summary.liveCoveragePct || 0}%<small>{liveCount} of {summary.totalPosts} placements have cached public Instagram metrics.</small></div>
          <div className="progress"><span style={{ width: `${Math.min(100, Number(summary.liveCoveragePct || 0))}%` }} /></div>
          <div className="insight-chip"><Pill>Cache first</Pill> Refreshing the browser uses the persisted cache and does not trigger Instagram scraping again.</div>
        </div>

        <div className="panel compact">
          <div className="mini-title">Campaign snapshot</div>
          <div className="snapshot-list">
            <div><span>Creators</span><strong>{summary.totalCreators}</strong></div>
            <div><span>Deliverables</span><strong>{summary.totalPosts}</strong></div>
            <div><span>Recorded reach</span><strong>{fmt(summary.totalReach)}</strong></div>
            <div><span>Public live views</span><strong>{fmt(summary.liveViews || 0)}</strong></div>
            <div><span>Categories</span><strong>{categories.length}</strong></div>
          </div>
        </div>
      </div>
    </div>
  )
}
