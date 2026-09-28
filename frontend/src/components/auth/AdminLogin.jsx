import { LockKeyhole } from 'lucide-react'
import { useState } from 'react'

export default function AdminLogin({ onLogin, error: externalError }) {
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const ok = await onLogin(key)
      if (!ok) setError('Invalid admin key.')
    } catch (err) {
      setError(err?.message || 'Admin login failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="admin-login-page">
      <form className="admin-login-card" onSubmit={submit}>
        <div className="brand-mark large">M</div>
        <div className="eyebrow">Monk-E internal workspace</div>
        <h1>Admin access</h1>
        <p>Campaign management, live sync and AI analysis are available only to internal users.</p>
        <label className="field-label">Admin key</label>
        <input className="text-input" type="password" value={key} onChange={e => setKey(e.target.value)} placeholder="Enter MONKE_ADMIN_KEY" autoFocus />
        {(error || externalError) && <div className="error-banner">{error || externalError}</div>}
        <button className="primary-btn wide" disabled={busy || !key.trim()}><LockKeyhole size={15} />{busy ? 'Checking…' : 'Open workspace'}</button>
      </form>
    </div>
  )
}
