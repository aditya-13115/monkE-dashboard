import { Check, Copy, FileSpreadsheet, Link2, Trash2, UploadCloud } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { SectionHeader, Pill } from '../../components/common/UI'
import { apiJson, endpoints } from '../../lib/api'

export default function Workspace({ grouped, refreshCatalog }) {
  const [brand, setBrand] = useState('')
  const [campaign, setCampaign] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [shareLinks, setShareLinks] = useState([])
  const [shareSelection, setShareSelection] = useState({})
  const [copied, setCopied] = useState('')

  const brands = useMemo(() => grouped.map(group => group.brand), [grouped])

  async function loadLinks() {
    try {
      const data = await apiJson(endpoints.shareLinks())
      setShareLinks(data?.links || [])
    } catch (err) {
      setError(err?.message || 'Could not load share links')
    }
  }

  useEffect(() => { loadLinks() }, [grouped.length])

  async function upload(event) {
    event.preventDefault()
    if (!brand.trim() || !campaign.trim() || !file) return
    setBusy(true); setError(''); setMessage('')
    try {
      const body = new FormData()
      body.append('brand', brand.trim())
      body.append('campaign', campaign.trim())
      body.append('file', file)
      await apiJson(endpoints.uploadCampaign(), { method: 'POST', body })
      setMessage(`Added ${brand.trim()} / ${campaign.trim()}.`)
      setCampaign(''); setFile(null)
      const input = document.getElementById('campaign-file-input')
      if (input) input.value = ''
      await refreshCatalog()
    } catch (err) {
      setError(err?.message || 'Campaign upload failed')
    } finally {
      setBusy(false)
    }
  }

  async function removeCampaign(item) {
    if (!window.confirm(`Delete ${item.brand} / ${item.campaign}? This removes the registered Excel file from the app workspace.`)) return
    setError(''); setMessage('')
    try {
      await apiJson(endpoints.deleteCampaign(item.id), { method: 'DELETE' })
      setMessage(`Deleted ${item.brand} / ${item.campaign}.`)
      await refreshCatalog(); await loadLinks()
    } catch (err) {
      setError(err?.message || 'Delete failed')
    }
  }

  function toggleShare(id) {
    setShareSelection(prev => {
      const next = { ...prev }
      next[id] = !next[id]
      return next
    })
  }

  function selectedIds(group) {
    const explicit = group.campaigns.filter(item => shareSelection[item.id]).map(item => item.id)
    return explicit.length ? explicit : group.campaigns.map(item => item.id)
  }

  async function createShare(group) {
    setError(''); setMessage('')
    try {
      const data = await apiJson(endpoints.shareLinks(), {
        method: 'POST',
        body: JSON.stringify({ brand: group.brand, campaignIds: selectedIds(group), label: `${group.brand} read-only view` }),
      })
      setMessage(`Read-only share created for ${group.brand}.`)
      await loadLinks()
      await navigator.clipboard?.writeText(data.url)
    } catch (err) {
      setError(err?.message || 'Could not create share link')
    }
  }

  async function deleteLink(token) {
    try {
      await apiJson(endpoints.deleteShareLink(token), { method: 'DELETE' })
      await loadLinks()
    } catch (err) {
      setError(err?.message || 'Could not delete share link')
    }
  }

  async function copy(url) {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(url)
      setTimeout(() => setCopied(''), 1600)
    } catch {}
  }

  return (
    <div className="page workspace-page">
      <SectionHeader eyebrow="Workspace administration" title="Brands & campaigns" copy="Excel is the campaign input. Add a brand, add one campaign file, and the dashboard registry keeps the hierarchy separate." />

      {(message || error) && <div className={error ? 'error-banner' : 'success-banner'}>{error || message}</div>}

      <div className="grid-two workspace-grid">
        <form className="panel upload-card" onSubmit={upload}>
          <SectionHeader eyebrow="Add campaign" title="Upload Excel" copy="Only .xlsx and .xlsm files are accepted. The workbook is validated before it becomes selectable." />
          <label className="field-label">Brand</label>
          <input className="text-input" value={brand} onChange={e => setBrand(e.target.value)} placeholder="e.g. Asian Paints" list="known-brands" />
          <datalist id="known-brands">{brands.map(item => <option key={item} value={item} />)}</datalist>
          <label className="field-label">Campaign</label>
          <input className="text-input" value={campaign} onChange={e => setCampaign(e.target.value)} placeholder="e.g. Summer Campaign" />
          <label className="field-label">Excel workbook</label>
          <label className="file-drop" htmlFor="campaign-file-input">
            <UploadCloud size={22} />
            <strong>{file?.name || 'Choose an Excel file'}</strong>
            <span>Workbook is copied into the campaign store after validation.</span>
          </label>
          <input id="campaign-file-input" className="hidden-file" type="file" accept=".xlsx,.xlsm" onChange={e => setFile(e.target.files?.[0] || null)} />
          <button className="primary-btn wide" disabled={busy || !brand.trim() || !campaign.trim() || !file}><FileSpreadsheet size={15} />{busy ? 'Validating…' : 'Add campaign'}</button>
        </form>

        <div className="panel hierarchy-card">
          <SectionHeader eyebrow="Registry" title="Brand → campaign hierarchy" copy="Each campaign has its own Excel source and cache namespace." />
          <div className="hierarchy-list">
            {grouped.length ? grouped.map(group => (
              <div className="brand-group" key={group.brand}>
                <div className="brand-group-head"><div><strong>{group.brand}</strong><span>{group.campaigns.length} campaign{group.campaigns.length === 1 ? '' : 's'}</span></div><button className="ghost-btn" onClick={() => createShare(group)}><Link2 size={13} /> Share selected</button></div>
                {group.campaigns.map(item => (
                  <div className="campaign-row" key={item.id}>
                    <label className="share-check"><input type="checkbox" checked={Boolean(shareSelection[item.id])} onChange={() => toggleShare(item.id)} /><span /></label>
                    <div className="campaign-row-icon"><FileSpreadsheet size={15} /></div>
                    <div className="campaign-row-main"><strong>{item.campaign}</strong><span>{item.recordCount} post rows • {item.sourceName}</span></div>
                    <button className="icon-btn danger" title="Delete campaign" onClick={() => removeCampaign(item)}><Trash2 size={15} /></button>
                  </div>
                ))}
              </div>
            )) : <div className="empty-panel"><h3>No campaigns registered</h3><p>Upload the first Excel workbook to create a brand and campaign.</p></div>}
          </div>
        </div>
      </div>

      <div className="panel share-links-card">
        <SectionHeader eyebrow="Read-only sharing" title="Brand POC links" copy="These links open the viewer-only experience. They have no upload, delete, live-refresh or AI-analysis controls." />
        {shareLinks.length ? <div className="share-link-list">
          {shareLinks.map(item => (
            <div className="share-link-row" key={item.token}>
              <div className="share-link-icon"><Link2 size={15} /></div>
              <div className="share-link-main"><strong>{item.label || item.brand}</strong><span>{item.brand} • {item.campaignIds?.length || 0} campaign(s)</span><a href={item.url} target="_blank" rel="noreferrer">{item.url}</a></div>
              <Pill>READ ONLY</Pill>
              <button className="ghost-btn" onClick={() => copy(item.url)}>{copied === item.url ? <Check size={13} /> : <Copy size={13} />}{copied === item.url ? 'Copied' : 'Copy'}</button>
              <button className="icon-btn danger" onClick={() => deleteLink(item.token)}><Trash2 size={14} /></button>
            </div>
          ))}
        </div> : <div className="muted">No share links created yet.</div>}
      </div>
    </div>
  )
}
