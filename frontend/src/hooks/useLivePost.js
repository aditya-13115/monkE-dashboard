import { useCallback, useState } from 'react'
import { apiJson, endpoints } from '../lib/api'
import { cacheKeys, readCache, writeCache } from '../lib/cache'

const inflight = new Map()
const memory = new Map()

function cacheId(campaignId, id) { return `${campaignId}:${id}` }

function cachedPost(campaignId, id) {
  const key = cacheId(campaignId, id)
  if (memory.has(key)) return memory.get(key)
  const disk = readCache(cacheKeys.livePost(campaignId, id))
  if (disk) {
    memory.set(key, disk)
    return disk
  }
  return null
}

export function useLivePost() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const fetchLivePost = useCallback(async (campaignId, id, force = false) => {
    if (!force) {
      const cached = cachedPost(campaignId, id)
      if (cached) return cached
    }

    const requestKey = cacheId(campaignId, id)
    if (!force && inflight.has(requestKey)) return inflight.get(requestKey)

    setBusy(true)
    setError('')
    const request = apiJson(endpoints.livePost(campaignId, id, force))
      .then(data => {
        const post = data.post
        memory.set(requestKey, post)
        writeCache(cacheKeys.livePost(campaignId, id), post)
        return post
      })
      .catch(err => {
        setError(err?.message || 'Live Instagram fetch failed')
        throw err
      })
      .finally(() => {
        inflight.delete(requestKey)
        setBusy(false)
      })

    inflight.set(requestKey, request)
    return request
  }, [])

  return { fetchLivePost, busy, error }
}

export function seedLivePost(campaignId, post) {
  if (!post?.id) return
  const key = cacheId(campaignId, post.id)
  memory.set(key, post)
  writeCache(cacheKeys.livePost(campaignId, post.id), post)
}
