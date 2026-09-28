import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiJson, endpoints } from '../lib/api'

const STORAGE_KEY = 'monke-selected-campaign-v6'

export function readSelectedCampaignId() {
  try { return sessionStorage.getItem(STORAGE_KEY) || localStorage.getItem(STORAGE_KEY) } catch { return null }
}

export function saveSelectedCampaignId(id) {
  try { localStorage.setItem(STORAGE_KEY, id) } catch {}
}

export function useCampaignCatalog() {
  const [campaigns, setCampaigns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setError('')
    try {
      const data = await apiJson(endpoints.adminCampaigns())
      const next = Array.isArray(data?.campaigns) ? data.campaigns : []
      setCampaigns(next)
      return next
    } catch (err) {
      setError(err?.message || 'Campaign registry unavailable')
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const grouped = useMemo(() => {
    const map = new Map()
    for (const item of campaigns) {
      if (!map.has(item.brand)) map.set(item.brand, [])
      map.get(item.brand).push(item)
    }
    return [...map.entries()].map(([brand, items]) => ({ brand, campaigns: items }))
  }, [campaigns])

  return { campaigns, grouped, loading, error, refresh }
}
