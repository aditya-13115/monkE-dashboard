const PREFIX = 'monke-campaign-v6:'

function safeParse(value) {
  if (!value) return null
  try { return JSON.parse(value) } catch { return null }
}

export function readCache(key) {
  try { return safeParse(localStorage.getItem(`${PREFIX}${key}`)) } catch { return null }
}

export function writeCache(key, value) {
  try { localStorage.setItem(`${PREFIX}${key}`, JSON.stringify(value)) } catch {}
}

export function removeCache(key) {
  try { localStorage.removeItem(`${PREFIX}${key}`) } catch {}
}

export const cacheKeys = {
  campaign: id => `campaign:${id || 'default'}`,
  selectedSentimentPost: campaignId => `selected-sentiment:${campaignId}`,
  sentiment: (campaignId, id) => `sentiment:${campaignId}:${id}`,
  livePost: (campaignId, id) => `live-post:${campaignId}:${id}`,
  campaignSentiment: campaignId => `campaign-sentiment:${campaignId}`,
}
