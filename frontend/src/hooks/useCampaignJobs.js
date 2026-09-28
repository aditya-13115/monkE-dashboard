import { useCallback, useEffect, useRef, useState } from 'react'
import { apiJson, endpoints } from '../lib/api'
import { cacheKeys, readCache, writeCache } from '../lib/cache'

const poll = (fn, ms = 1500) => window.setInterval(fn, ms)

export function useCampaignSync(campaignId, onComplete) {
  const [job, setJob] = useState(null)
  const timer = useRef(null)

  const clear = useCallback(() => {
    if (timer.current) window.clearInterval(timer.current)
    timer.current = null
  }, [])

  useEffect(() => clear, [clear])

  const start = useCallback(async (force = true) => {
    if (!campaignId || job?.status === 'running' || job?.status === 'queued') return
    clear()
    const initial = await apiJson(endpoints.syncCampaign(campaignId, force), { method: 'POST' })
    setJob(initial)
    if (initial.status === 'complete' || initial.status === 'failed') return initial

    const tick = async () => {
      try {
        const status = await apiJson(endpoints.syncStatus(campaignId, initial.jobId))
        setJob(status)
        if (status.status === 'complete' || status.status === 'failed') {
          clear()
          if (status.status === 'complete') await onComplete?.(status)
        }
      } catch (error) {
        setJob(prev => ({ ...(prev || initial), status: 'failed', error: error?.message || 'Sync status failed' }))
        clear()
      }
    }
    timer.current = poll(tick)
    await tick()
    return initial
  }, [campaignId, clear, job?.status, onComplete])

  return { job, start, running: job?.status === 'queued' || job?.status === 'running' }
}

export function useCampaignSentiment(campaignId, initialResult = null, useLocalCache = true) {
  const cached = useLocalCache ? readCache(cacheKeys.campaignSentiment(campaignId)) : null
  const [result, setResult] = useState(initialResult || cached || null)
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const timer = useRef(null)

  const clear = useCallback(() => {
    if (timer.current) window.clearInterval(timer.current)
    timer.current = null
  }, [])

  useEffect(() => {
    setResult(initialResult || (useLocalCache ? readCache(cacheKeys.campaignSentiment(campaignId)) : null) || null)
    setError('')
    clear()
  }, [campaignId, initialResult, clear, useLocalCache])

  useEffect(() => clear, [clear])

  const start = useCallback(async (force = false) => {
    if (!campaignId || job?.status === 'running' || job?.status === 'queued') return
    setError('')
    clear()
    try {
      const initial = await apiJson(endpoints.startCampaignSentiment(campaignId, force), { method: 'POST' })
      if (initial?.result && initial.status === 'complete') {
        setResult(initial.result)
        writeCache(cacheKeys.campaignSentiment(campaignId), initial.result)
        setJob(initial)
        return initial
      }
      setJob(initial)
      const tick = async () => {
        try {
          const status = await apiJson(endpoints.campaignSentimentStatus(campaignId, initial.jobId))
          setJob(status)
          if (status.status === 'complete') {
            const next = status.result || null
            setResult(next)
            if (next) writeCache(cacheKeys.campaignSentiment(campaignId), next)
            clear()
          } else if (status.status === 'failed') {
            setError(status.error || 'Campaign sentiment failed')
            clear()
          }
        } catch (err) {
          setError(err?.message || 'Campaign sentiment status failed')
          clear()
        }
      }
      timer.current = poll(tick)
      await tick()
      return initial
    } catch (err) {
      setError(err?.message || 'Could not start campaign sentiment')
      throw err
    }
  }, [campaignId, clear, job?.status])

  return { result, job, error, start, running: job?.status === 'queued' || job?.status === 'running' }
}
