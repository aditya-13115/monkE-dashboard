import { useCallback, useEffect, useState } from 'react'
import { endpoints, apiJson } from '../lib/api'
import { cacheKeys, readCache, writeCache } from '../lib/cache'

export function useCampaign(campaignId) {
  const cacheKey = cacheKeys.campaign(campaignId)
  const [campaign, setCampaign] = useState(() => readCache(cacheKey))
  const [loading, setLoading] = useState(!campaign)
  const [error, setError] = useState('')
  const [cached, setCached] = useState(Boolean(campaign))

  useEffect(() => {
    setCampaign(readCache(cacheKey))
    setCached(Boolean(readCache(cacheKey)))
    setLoading(!readCache(cacheKey))
    setError('')
  }, [cacheKey])

  const refresh = useCallback(async () => {
    if (!campaignId) {
      setLoading(false)
      return null
    }
    setError('')
    try {
      const data = await apiJson(endpoints.campaign(campaignId))
      setCampaign(data)
      writeCache(cacheKey, data)
      setCached(Boolean(readCache(cacheKey)))
      return data
    } catch (err) {
      setError(err?.message || 'Campaign API unavailable')
      return null
    } finally {
      setLoading(false)
    }
  }, [campaignId, cacheKey])

  useEffect(() => { refresh() }, [refresh])

  return { campaign, setCampaign, loading, error, cached, refresh }
}
