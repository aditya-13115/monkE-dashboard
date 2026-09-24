const PREFIX = 'monke-campaign-v5:'

function safeParse(value) {
  if (!value) return null
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

export function readCache(key) {
  try {
    return safeParse(localStorage.getItem(`${PREFIX}${key}`))
  } catch {
    return null
  }
}

export function writeCache(key, value) {
  try {
    localStorage.setItem(`${PREFIX}${key}`, JSON.stringify(value))
  } catch {
    // Storage quota/private mode should never break the dashboard.
  }
}

export function removeCache(key) {
  try {
    localStorage.removeItem(`${PREFIX}${key}`)
  } catch {
    // Ignore storage errors.
  }
}

export const cacheKeys = {
  campaign: 'campaign',
  selectedSentimentPost: 'selected-sentiment-post',
  sentiment: id => `sentiment:${id}`,
  livePost: id => `live-post:${id}`,
}
