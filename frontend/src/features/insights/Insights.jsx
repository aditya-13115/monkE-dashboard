import { Activity, Bot, Target } from 'lucide-react'
import { SectionHeader, Metric } from '../../components/common/UI'
import { fmt, pct, publicEngagement } from '../../lib/metrics'

export default function Insights({ campaign }) {
  const { records, summary } = campaign
  const topReach = [...records].sort((a, b) => b.reach - a.reach)[0]
  const topER = [...records].sort((a, b) => {
    const ea = a.liveDataAvailable ? a.liveEngagementRateReach : a.engagementRateReach
    const eb = b.liveDataAvailable ? b.liveEngagementRateReach : b.engagementRateReach
    return eb - ea
  })[0]
  const topEng = [...records].sort((a, b) => publicEngagement(b) - publicEngagement(a))[0]
  const top10Reach = [...records].sort((a, b) => b.reach - a.reach).slice(0, 10).reduce((sum, row) => sum + Number(row.reach || 0), 0)
  const concentration = summary.totalReach ? top10Reach / summary.totalReach * 100 : 0

  return (
    <div className="page">
      <SectionHeader eyebrow="Decision support" title="Campaign Insights" copy="Signals are calculated from campaign workbook rows plus any persisted public Instagram metrics; no synthetic performance numbers are introduced." />
      <div className="grid-three">
        <div className="insight-card"><div className="insight-label">Scale signal</div><h3>@{topReach?.username}</h3><p>Highest recorded reach at <strong>{fmt(topReach?.reach)}</strong>.</p><span>{topReach?.category} • workbook reach</span></div>
        <div className="insight-card"><div className="insight-label">Interaction signal</div><h3>@{topER?.username}</h3><p>Highest public engagement-to-recorded-reach rate at <strong>{pct(topER?.liveDataAvailable ? topER.liveEngagementRateReach : topER?.engagementRateReach)}</strong>.</p><span>{topER?.liveDataAvailable ? 'Instagram public engagement' : 'Workbook engagement'}</span></div>
        <div className="insight-card"><div className="insight-label">Engagement volume</div><h3>@{topEng?.username}</h3><p>Highest available engagement at <strong>{fmt(publicEngagement(topEng))}</strong>.</p><span>{topEng?.liveDataAvailable ? 'Public Instagram' : 'Workbook fallback'}</span></div>
      </div>
      <div className="grid-three">
        <Metric icon={Target} label="Reach concentration" value={`${concentration.toFixed(1)}%`} sub="Top 10 placements / recorded reach" accent="violet" />
        <Metric icon={Activity} label="Live posts" value={fmt(summary.livePostsSynced)} sub={`${summary.liveCoveragePct || 0}% cache coverage`} accent="mint" />
        <Metric icon={Bot} label="Live public views" value={fmt(summary.liveViews)} sub="Only from synced posts" accent="blue" />
      </div>
      <div className="grid-two">
        <div className="panel">
          <SectionHeader eyebrow="Concentration" title="How concentrated is recorded reach?" />
          <div className="big-stat">{concentration.toFixed(1)}%<small>of total recorded reach comes from the top 10 placements.</small></div>
          <div className="progress"><span style={{ width: `${Math.min(100, concentration)}%` }} /></div>
          <p className="muted">This diagnostic uses the campaign workbook because public Instagram pages do not expose owner-only reach reliably.</p>
        </div>
        <div className="panel">
          <SectionHeader eyebrow="Operational flow" title="Data handling" />
          <div className="check-list">
            <div><span className="check">01</span><strong>Excel remains source of truth</strong><p>Follower base, recorded reach, creator identity and POST LINK come from the workbook.</p></div>
            <div><span className="check">02</span><strong>Instagram is cached persistently</strong><p>Public likes, comments, views and thumbnails are stored locally after a successful scrape.</p></div>
            <div><span className="check">03</span><strong>AI analysis is cached separately</strong><p>Groq is not called again when a post already has a valid sentiment result in cache.</p></div>
          </div>
        </div>
      </div>
    </div>
  )
}
