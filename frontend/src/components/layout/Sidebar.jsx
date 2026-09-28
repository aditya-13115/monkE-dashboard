import { BarChart3, Bot, BriefcaseBusiness, Instagram, LayoutDashboard, Settings2, Sparkles, Users } from 'lucide-react'
import { Pill } from '../common/UI'

export const navItems = [
  ['overview', 'Overview', LayoutDashboard],
  ['posts', 'Post Explorer', Instagram],
  ['creators', 'Creator Analytics', Users],
  ['categories', 'Category Insights', BarChart3],
  ['sentiment', 'AI Sentiment', Bot],
  ['insights', 'Campaign Insights', Sparkles],
  ['workspace', 'Brands & Campaigns', BriefcaseBusiness],
]

export default function Sidebar({ active, onNavigate, grouped, selectedCampaignId, onSelectCampaign }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">M</div>
        <div><strong>monk-e</strong><span>campaign intelligence</span></div>
      </div>

      <div className="campaign-tree">
        <div className="campaign-tree-label">Campaign workspace</div>
        {grouped.map(group => (
          <div className="tree-brand" key={group.brand}>
            <strong>{group.brand}</strong>
            <div>
              {group.campaigns.map(item => (
                <button key={item.id} className={selectedCampaignId === item.id ? 'tree-campaign active' : 'tree-campaign'} onClick={() => onSelectCampaign(item.id)}>
                  <span className="tree-dot" />{item.campaign}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <nav>
        {navItems.map(([key, label, Icon]) => (
          <button key={key} className={active === key ? 'active' : ''} onClick={() => onNavigate(key)}>
            <Icon size={17} />
            <span>{label}</span>
            {key === 'sentiment' && <Pill>AI</Pill>}
            {key === 'workspace' && <Settings2 size={13} className="nav-trailing" />}
          </button>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <div className="status-dot" />
        <div>
          <strong>Multi-campaign workspace</strong>
          <span>{grouped.reduce((sum, group) => sum + group.campaigns.length, 0)} campaigns registered</span>
        </div>
      </div>
    </aside>
  )
}
