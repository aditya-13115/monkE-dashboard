import { useCallback, useEffect, useState } from 'react'
import { endpoints, apiJson } from '../lib/api'
import { cacheKeys, readCache, writeCache } from '../lib/cache'

export function useCampaign() {
  const [campaign, setCampaign] = useState(() => readCache(cacheKeys.campaign))
  const [loading, setLoading] = useState(!campaign)
  const [error, setError] = useState('')
  const [cached, setCached] = useState(Boolean(campaign))

  const refresh = useCallback(async () => {
    setError('')
    try {
      const data = await apiJson(endpoints.campaign())
      setCampaign(data)
      writeCache(cacheKeys.campaign, data)
      setCached(true)
      return data
    } catch (err) {
      setError(err?.message || 'Campaign API unavailable')
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // The backend itself is persistent-cache aware. This request is cheap and
    // also picks up any newly synced Instagram records without forcing live scraping.
    refresh()
  }, [refresh])

  return { campaign, setCampaign, loading, error, cached, refresh }
}
