import { LogOut, RefreshCw } from 'lucide-react'
import { navItems } from './Sidebar'
import { useCampaignSync } from '../../hooks/useCampaignJobs'

export default function Topbar({ active, campaign, campaignId, onRefresh, refreshing, onLogout, showLogout, onSynced }) {
  const label = navItems.find(item => item[0] === active)?.[1] || 'Overview'
  const coverage = Number(campaign?.summary?.livePostsSynced || 0)
  const total = Number(campaign?.summary?.totalPosts || 0)
  const { job: syncJob, start: startSync, running: syncing } = useCampaignSync(campaignId, onSynced)
  const syncLabel = syncing ? `Fetching ${syncJob?.processed || 0}/${syncJob?.total || total}` : syncJob?.status === 'complete' ? 'Sync complete' : 'Fetch all Instagram'
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">Monk-E / {campaign?.meta?.brand || 'Campaign dashboard'}</span>
        <h1>{label}</h1>
        {campaign?.meta?.campaign && <span className="topbar-campaign">{campaign.meta.campaign}</span>}
      </div>
      <div className="top-actions">
        <div className="live-pill" title="Dashboard reload uses persisted campaign and Instagram caches; it does not force scraping.">
          <span className="status-dot" />
          {coverage > 0 ? `Live cache ${coverage}/${total}` : 'Cached campaign data'}
        </div>
        {campaignId && <button className="ghost-btn top-refresh" onClick={() => startSync(true)} disabled={syncing}>
          <RefreshCw size={14} className={syncing ? 'spin' : ''} />
          {syncLabel}
        </button>}
        {onRefresh && <button className="ghost-btn top-refresh" onClick={onRefresh} disabled={refreshing || syncing}>
          <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
          {refreshing ? 'Refreshing…' : 'Refresh dashboard'}
        </button>}
        {showLogout && <button className="icon-btn" title="Clear admin key" onClick={onLogout}><LogOut size={15} /></button>}
      </div>
    </header>
  )
}
