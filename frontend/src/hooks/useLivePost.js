import { useCallback, useState } from 'react'
import { apiJson, endpoints } from '../lib/api'
import { cacheKeys, readCache, writeCache } from '../lib/cache'

const inflight = new Map()
const memory = new Map()

function cachedPost(id) {
  if (memory.has(id)) return memory.get(id)
  const disk = readCache(cacheKeys.livePost(id))
  if (disk) {
    memory.set(id, disk)
    return disk
  }
  return null
}

export function useLivePost() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const fetchLivePost = useCallback(async (id, force = false) => {
    if (!force) {
      const cached = cachedPost(id)
      if (cached) return cached
    }

    if (!force && inflight.has(id)) return inflight.get(id)

    setBusy(true)
    setError('')
    const request = apiJson(endpoints.livePost(id, force))
      .then(data => {
        const post = data.post
        memory.set(id, post)
        writeCache(cacheKeys.livePost(id), post)
        return post
      })
      .catch(err => {
        setError(err?.message || 'Live Instagram fetch failed')
        throw err
      })
      .finally(() => {
        inflight.delete(id)
        setBusy(false)
      })

    inflight.set(id, request)
    return request
  }, [])

  return { fetchLivePost, busy, error }
}

export function seedLivePost(post) {
  if (!post?.id) return
  memory.set(post.id, post)
  writeCache(cacheKeys.livePost(post.id), post)
}
