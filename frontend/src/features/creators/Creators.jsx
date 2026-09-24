import { useMemo, useState } from 'react'
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { SectionHeader } from '../../components/common/UI'
import { fmt, pct, publicEngagement } from '../../lib/metrics'

export default function Creators({ campaign }) {
  const [sort, setSort] = useState('reach')
  const rows = useMemo(() => [...campaign.records].sort((a, b) => Number(b[sort] || 0) - Number(a[sort] || 0)).slice(0, 25), [campaign.records, sort])
  const scatter = campaign.records.map(row => ({
    x: row.followers,
    y: row.reach,
    z: Math.max(12, publicEngagement(row)),
    name: row.username,
  }))

  return (
    <div className="page">
      <SectionHeader eyebrow="Creator intelligence" title="Creator Analytics" copy="Follower base and recorded reach come from Excel; bubble size uses persisted public Instagram engagement when available." />
      <div className="grid-two">
        <div className="panel">
          <SectionHeader eyebrow="Audience → outcome" title="Follower base vs reach" />
          <div className="chart"><ResponsiveContainer width="100%" height={340}>
            <ScatterChart margin={{ top: 10, right: 15, bottom: 10, left: 5 }}>
              <CartesianGrid strokeDasharray="4 4" />
              <XAxis type="number" dataKey="x" name="Followers" tickFormatter={fmt} tickLine={false} />
              <YAxis type="number" dataKey="y" name="Reach" tickFormatter={fmt} tickLine={false} />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={(value, name) => [fmt(value), name]} />
              <Scatter data={scatter} fill="#8b5cf6" />
            </ScatterChart>
          </ResponsiveContainer></div>
        </div>
        <div className="panel">
          <SectionHeader eyebrow="Performance table" title="Top creator placements" action={<div className="selectbox"><select value={sort} onChange={e => setSort(e.target.value)}><option value="reach">Reach</option><option value="engagement">Engagement</option><option value="engagementRateReach">Engagement rate</option></select></div>} />
          <div className="rank-list scroll">
            {rows.map((row, index) => {
              const engagement = publicEngagement(row)
              const er = row.liveDataAvailable ? row.liveEngagementRateReach : row.engagementRateReach
              return <div className="rank-row" key={row.id}>
                <div className="rank-num">{String(index + 1).padStart(2, '0')}</div>
                <div className="avatar">{row.username.slice(0, 2).toUpperCase()}</div>
                <div className="rank-main"><strong>@{row.username}</strong><span>{row.category}</span></div>
                <div className="stacked-value"><strong>{sort === 'reach' ? fmt(row.reach) : sort === 'engagement' ? fmt(engagement) : pct(er)}</strong><span>{sort === 'reach' ? 'reach' : sort === 'engagement' ? 'public engagement' : 'ER'}</span></div>
              </div>
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
