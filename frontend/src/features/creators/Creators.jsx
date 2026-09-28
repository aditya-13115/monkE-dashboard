import { useMemo, useState } from 'react'
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { SectionHeader } from '../../components/common/UI'
import { fmt, pct, publicEngagement } from '../../lib/metrics'

export default function Creators({ campaign }) {
  const [sort, setSort] = useState('liveViews')
  const rows = useMemo(() => [...campaign.records].sort((a, b) => Number(b[sort] || 0) - Number(a[sort] || 0)).slice(0, 25), [campaign.records, sort])
  const scatter = campaign.records.map(row => ({
    x: row.followers,
    y: Number(row.liveDataAvailable ? row.liveViews : row.reach || 0),
    z: Math.max(12, publicEngagement(row)),
    name: row.username,
  }))

  return (
    <div className="page">
      <SectionHeader eyebrow="Creator intelligence" title="Creator Analytics" copy="Follower base comes from Excel; the outcome axis uses public Instagram views after sync and falls back to workbook reach only before live data exists." />
      <div className="grid-two">
        <div className="panel">
          <SectionHeader eyebrow="Audience → outcome" title="Follower base vs public views" />
          <div className="chart"><ResponsiveContainer width="100%" height={340}>
            <ScatterChart margin={{ top: 10, right: 15, bottom: 10, left: 5 }}>
              <CartesianGrid strokeDasharray="4 4" />
              <XAxis type="number" dataKey="x" name="Followers" tickFormatter={fmt} tickLine={false} />
              <YAxis type="number" dataKey="y" name="Public views" tickFormatter={fmt} tickLine={false} />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={(value, name) => [fmt(value), name]} />
              <Scatter data={scatter} fill="#8b5cf6" />
            </ScatterChart>
          </ResponsiveContainer></div>
        </div>
        <div className="panel">
          <SectionHeader eyebrow="Performance table" title="Top creator placements" action={<div className="selectbox"><select value={sort} onChange={e => setSort(e.target.value)}><option value="liveViews">Public views</option><option value="reach">Recorded reach</option><option value="engagement">Engagement</option><option value="engagementRateReach">Engagement rate</option></select></div>} />
          <div className="rank-list scroll">
            {rows.map((row, index) => {
              const engagement = publicEngagement(row)
              const er = row.liveDataAvailable ? row.liveEngagementRateReach : row.engagementRateReach
              return <div className="rank-row" key={row.id}>
                <div className="rank-num">{String(index + 1).padStart(2, '0')}</div>
                <div className="avatar">{row.username.slice(0, 2).toUpperCase()}</div>
                <div className="rank-main"><strong>@{row.username}</strong><span>{row.category}</span></div>
                <div className="stacked-value"><strong>{sort === 'reach' ? fmt(row.reach) : sort === 'liveViews' ? fmt(row.liveViews) : sort === 'engagement' ? fmt(engagement) : pct(er)}</strong><span>{sort === 'reach' ? 'recorded reach' : sort === 'liveViews' ? 'public views' : sort === 'engagement' ? 'public engagement' : 'ER'}</span></div>
              </div>
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
