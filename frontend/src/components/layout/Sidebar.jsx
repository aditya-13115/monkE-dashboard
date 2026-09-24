import { BarChart3, Bot, Instagram, LayoutDashboard, Sparkles, Users } from 'lucide-react'
import { Pill } from '../common/UI'

export const navItems = [
  ['overview', 'Overview', LayoutDashboard],
  ['posts', 'Post Explorer', Instagram],
  ['creators', 'Creator Analytics', Users],
  ['categories', 'Category Insights', BarChart3],
  ['sentiment', 'AI Sentiment', Bot],
  ['insights', 'Campaign Insights', Sparkles],
]

export default function Sidebar({ active, onNavigate, campaign }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">M</div>
        <div><strong>monk-e</strong><span>campaign intelligence</span></div>
      </div>
      <div className="campaign-switch">
        <span>Active campaign</span>
        <strong>{campaign.meta.campaign}</strong>
        <small>{campaign.meta.platform} · {campaign.meta.date}</small>
      </div>
      <nav>
        {navItems.map(([key, label, Icon]) => (
          <button key={key} className={active === key ? 'active' : ''} onClick={() => onNavigate(key)}>
            <Icon size={17} />
            <span>{label}</span>
            {key === 'sentiment' && <Pill>AI</Pill>}
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="status-dot" />
        <div>
          <strong>Campaign data connected</strong>
          <span>{campaign.summary.totalPosts} placements loaded</span>
        </div>
      </div>
    </aside>
  )
}
