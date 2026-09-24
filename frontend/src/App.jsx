import { useCallback, useState } from 'react'
import { AlertCircle } from 'lucide-react'
import { useCampaign } from './hooks/useCampaign'
import Sidebar from './components/layout/Sidebar'
import Topbar from './components/layout/Topbar'
import { Loader } from './components/common/UI'
import Overview from './features/overview/Overview'
import Posts from './features/posts/Posts'
import Creators from './features/creators/Creators'
import Categories from './features/categories/Categories'
import SentimentPage from './features/sentiment/SentimentPage'
import Insights from './features/insights/Insights'

export default function App() {
  const { campaign, setCampaign, loading, error, cached, refresh } = useCampaign()
  const [active, setActive] = useState('overview')
  const [focusedId, setFocusedId] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  const navigate = useCallback((page, id = null) => {
    setActive(page)
    if (id != null) setFocusedId(id)
  }, [])

  async function refreshDashboard() {
    setRefreshing(true)
    try {
      await refresh()
    } finally {
      setRefreshing(false)
    }
  }

  if (!campaign && loading) return <Loader label="Loading campaign intelligence…" />

  if (!campaign) {
    return (
      <div className="loading error-loading">
        <AlertCircle size={28} />
        <strong>Campaign data is unavailable.</strong>
        <span>{error || 'Start the FastAPI backend and reload.'}</span>
        <button className="ghost-btn" onClick={refresh}>Retry</button>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <Sidebar active={active} onNavigate={navigate} campaign={campaign} />
      <main className="main">
        <Topbar active={active} campaign={campaign} onRefresh={refreshDashboard} refreshing={refreshing} />
        {cached && error && <div className="cache-warning">Showing persisted dashboard cache. Backend refresh failed: {error}</div>}
        {active === 'overview' && <Overview campaign={campaign} onGo={navigate} />}
        {active === 'posts' && <Posts campaign={campaign} focusedId={focusedId} />}
        {active === 'creators' && <Creators campaign={campaign} />}
        {active === 'categories' && <Categories campaign={campaign} />}
        {active === 'sentiment' && <SentimentPage campaign={campaign} setCampaign={setCampaign} />}
        {active === 'insights' && <Insights campaign={campaign} />}
      </main>
    </div>
  )
}
