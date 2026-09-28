import { Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { SectionHeader, Pill } from '../../components/common/UI'
import { fmt, pct } from '../../lib/metrics'

export default function Categories({ campaign }) {
  const rows = campaign.categories.map(category => ({
    ...category,
    publicViews: category.livePosts ? category.liveViews : 0,
    publicEngagement: category.livePosts ? category.liveEngagement : 0,
    publicER: category.livePosts ? category.liveEngagementRate : 0,
    publicShare: campaign.summary.liveViews ? (Number(category.liveViews || 0) / Number(campaign.summary.liveViews || 1)) * 100 : 0,
  }))

  return (
    <div className="page">
      <SectionHeader eyebrow="Category intelligence" title="Category Insights" copy="The cards and graph use live public Instagram views and engagement after the campaign sync. Workbook reach remains visible separately." />
      <div className="grid-three">
        {rows.map(category => (
          <div className="panel category-card" key={category.name}>
            <div className="category-top"><Pill>{category.name}</Pill><span>{category.creators} placements</span></div>
            <div className="category-hero">{fmt(category.publicViews)}<small>public views</small></div>
            <div className="progress"><span style={{ width: `${Math.min(100, category.publicShare)}%` }} /></div>
            <div className="category-stats">
              <div><span>Public engagement</span><strong>{fmt(category.publicEngagement)}</strong></div>
              <div><span>ER / reach</span><strong>{pct(category.publicER)}</strong></div>
              <div><span>Recorded reach</span><strong>{fmt(category.reach)}</strong></div>
              <div><span>Live coverage</span><strong>{category.livePosts}/{category.deliverables}</strong></div>
            </div>
          </div>
        ))}
      </div>
      <div className="panel">
        <SectionHeader eyebrow="Live + recorded efficiency" title="Public views vs public engagement by category" />
        <div className="chart"><ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
            <CartesianGrid strokeDasharray="4 4" vertical={false} />
            <XAxis dataKey="name" tickLine={false} axisLine={false} />
            <YAxis yAxisId="left" tickFormatter={fmt} tickLine={false} axisLine={false} />
            <YAxis yAxisId="right" orientation="right" tickFormatter={v => `${v}%`} tickLine={false} axisLine={false} />
            <Tooltip formatter={(value, name) => [name === 'publicER' ? `${value}%` : fmt(value), name]} />
            <Bar yAxisId="left" dataKey="publicViews" radius={[8, 8, 0, 0]} fill="#8b5cf6" name="Public views" />
            <Line yAxisId="left" type="monotone" dataKey="publicEngagement" stroke="#10b981" strokeWidth={3} dot={{ r: 4 }} name="Public engagement" />
            <Line yAxisId="right" type="monotone" dataKey="publicER" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} name="ER / reach" />
          </ComposedChart>
        </ResponsiveContainer></div>
      </div>
    </div>
  )
}
