import { RefreshCw } from 'lucide-react'
import { navItems } from './Sidebar'
import { ageLabel } from '../../lib/metrics'

export default function Topbar({ active, campaign, onRefresh, refreshing }) {
  const label = navItems.find(item => item[0] === active)?.[1] || 'Overview'
  const coverage = Number(campaign?.summary?.livePostsSynced || 0)
  const total = Number(campaign?.summary?.totalPosts || 0)
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">Monk-E / Campaign dashboard</span>
        <h1>{label}</h1>
      </div>
      <div className="top-actions">
        <div className="live-pill" title="Reload uses persisted campaign/live caches; it does not force Instagram scraping.">
          <span className="status-dot" />
          {coverage > 0 ? `Live cache ${coverage}/${total}` : 'Cached campaign data'}
        </div>
        <button className="ghost-btn top-refresh" onClick={onRefresh} disabled={refreshing}>
          <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
          {refreshing ? 'Refreshing…' : 'Refresh dashboard'}
        </button>
      </div>
    </header>
  )
}
