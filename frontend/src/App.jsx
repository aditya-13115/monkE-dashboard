import { useCallback, useEffect, useState } from 'react'
import { AlertCircle } from 'lucide-react'
import AdminLogin from './components/auth/AdminLogin'
import Sidebar from './components/layout/Sidebar'
import Topbar from './components/layout/Topbar'
import { Loader } from './components/common/UI'
import Overview from './features/overview/Overview'
import Posts from './features/posts/Posts'
import Creators from './features/creators/Creators'
import Categories from './features/categories/Categories'
import SentimentPage from './features/sentiment/SentimentPage'
import Insights from './features/insights/Insights'
import Workspace from './features/workspace/Workspace'
import ViewerApp from './features/viewer/ViewerApp'
import { useAdminAuth } from './hooks/useAdminAuth'
import { readSelectedCampaignId, saveSelectedCampaignId, useCampaignCatalog } from './hooks/useCampaignCatalog'
import { useCampaign } from './hooks/useCampaign'

function isViewerRoute() {
  return window.location.pathname.startsWith('/share/')
}

function AdminApp() {
  const auth = useAdminAuth()
  const catalog = useCampaignCatalog()
  const [active, setActive] = useState('overview')
  const [focusedId, setFocusedId] = useState(null)
  const [selectedCampaignId, setSelectedCampaignId] = useState(() => readSelectedCampaignId())
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    if (!catalog.campaigns.length) {
      if (!catalog.loading) setActive('workspace')
      return
    }
    const exists = catalog.campaigns.some(item => item.id === selectedCampaignId)
    if (!exists) {
      setSelectedCampaignId(catalog.campaigns[0].id)
      saveSelectedCampaignId(catalog.campaigns[0].id)
    }
  }, [catalog.campaigns, catalog.loading, selectedCampaignId])

  const { campaign, setCampaign, loading, error, cached, refresh } = useCampaign(selectedCampaignId)

  useEffect(() => {
    if (!auth.loading && auth.valid) catalog.refresh()
  }, [auth.loading, auth.valid])

  const navigate = useCallback((page, id = null) => {
    setActive(page)
    if (id != null) setFocusedId(id)
  }, [])

  function selectCampaign(id) {
    setSelectedCampaignId(id)
    saveSelectedCampaignId(id)
    setFocusedId(null)
    if (active === 'workspace') setActive('overview')
  }

  async function refreshDashboard() {
    setRefreshing(true)
    try { await refresh() } finally { setRefreshing(false) }
  }

  const workspaceOnly = active === 'workspace'

  if (auth.loading || catalog.loading) return <Loader label="Loading Monk-E workspace…" />
  if (auth.enabled && !auth.valid) return <AdminLogin onLogin={auth.login} error={catalog.error || auth.error} />

  if (!workspaceOnly && !campaign && loading) return <Loader label="Loading campaign intelligence…" />

  if (!workspaceOnly && !campaign) {
    return (
      <div className="loading error-loading">
        <AlertCircle size={28} />
        <strong>Campaign data is unavailable.</strong>
        <span>{error || 'Choose a campaign from the workspace.'}</span>
        <button className="ghost-btn" onClick={catalog.refresh}>Retry</button>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <Sidebar active={active} onNavigate={navigate} grouped={catalog.grouped} selectedCampaignId={selectedCampaignId} onSelectCampaign={selectCampaign} />
      <main className="main">
        <Topbar active={active} campaign={campaign} onRefresh={workspaceOnly ? null : refreshDashboard} refreshing={refreshing} onLogout={auth.logout} showLogout={auth.enabled} />
        {cached && error && !workspaceOnly && <div className="cache-warning">Showing persisted dashboard cache. Backend refresh failed: {error}</div>}
        {active === 'overview' && campaign && <Overview campaign={campaign} onGo={navigate} />}
        {active === 'posts' && campaign && <Posts campaign={campaign} campaignId={selectedCampaignId} focusedId={focusedId} />}
        {active === 'creators' && campaign && <Creators campaign={campaign} />}
        {active === 'categories' && campaign && <Categories campaign={campaign} />}
        {active === 'sentiment' && campaign && <SentimentPage campaign={campaign} campaignId={selectedCampaignId} setCampaign={setCampaign} />}
        {active === 'insights' && campaign && <Insights campaign={campaign} />}
        {active === 'workspace' && <Workspace grouped={catalog.grouped} refreshCatalog={catalog.refresh} />}
      </main>
    </div>
  )
}

export default function App() {
  return isViewerRoute() ? <ViewerApp /> : <AdminApp />
}
