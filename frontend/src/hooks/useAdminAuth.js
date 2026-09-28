import { useCallback, useEffect, useState } from 'react'
import { apiJson, endpoints } from '../lib/api'

const KEY = 'monke-admin-key'

export function getAdminKey() {
  try { return sessionStorage.getItem(KEY) || '' } catch { return '' }
}

export function saveAdminKey(value) {
  try { sessionStorage.setItem(KEY, value) } catch {}
}

export function clearAdminKey() {
  try { sessionStorage.removeItem(KEY) } catch {}
}

export function useAdminAuth() {
  const [status, setStatus] = useState({ loading: true, enabled: false, valid: true })

  const check = useCallback(async () => {
    try {
      const config = await apiJson(endpoints.adminStatus())
      if (!config.authEnabled) {
        setStatus({ loading: false, enabled: false, valid: true })
        return true
      }
      const key = getAdminKey()
      if (!key) {
        setStatus({ loading: false, enabled: true, valid: false })
        return false
      }
      try {
        await apiJson(endpoints.adminCampaigns())
        setStatus({ loading: false, enabled: true, valid: true })
        return true
      } catch {
        clearAdminKey()
        setStatus({ loading: false, enabled: true, valid: false })
        return false
      }
    } catch (err) {
      setStatus({ loading: false, enabled: false, valid: false, error: err?.message || 'Backend unavailable' })
      return false
    }
  }, [])

  useEffect(() => { check() }, [check])

  const login = useCallback(async key => {
    saveAdminKey(key.trim())
    const ok = await check()
    if (!ok) clearAdminKey()
    return ok
  }, [check])

  const logout = useCallback(() => {
    clearAdminKey()
    setStatus(prev => ({ ...prev, valid: !prev.enabled }))
  }, [])

  return { ...status, login, logout, check }
}
