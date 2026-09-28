const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const ADMIN_KEY = 'monke-admin-key'

export { API }

function getAdminKey() {
  try { return sessionStorage.getItem(ADMIN_KEY) || '' } catch { return '' }
}

export async function apiJson(path, options = {}) {
  const headers = {
    Accept: 'application/json',
    ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers || {}),
  }
  const key = getAdminKey()
  if (key) headers['X-Admin-Key'] = key

  const response = await fetch(`${API}${path}`, { ...options, headers })
  let payload = null
  try { payload = await response.json() } catch { payload = null }
  if (!response.ok) throw new Error(payload?.detail || `Request failed (${response.status})`)
  return payload
}

export const endpoints = {
  adminStatus: () => '/api/admin/status',
  adminCampaigns: () => '/api/admin/campaigns',
  uploadCampaign: () => '/api/admin/campaigns/upload',
  deleteCampaign: id => `/api/admin/campaigns/${encodeURIComponent(id)}`,
  shareLinks: () => '/api/admin/share-links',
  deleteShareLink: token => `/api/admin/share-links/${encodeURIComponent(token)}`,
  campaign: id => id ? `/api/campaigns/${encodeURIComponent(id)}` : '/api/campaign',
  livePost: (campaignId, id, force = false) => `/api/campaigns/${encodeURIComponent(campaignId)}/posts/${id}/live${force ? '?force=true' : ''}`,
  syncCampaign: (campaignId, force = true) => `/api/campaigns/${encodeURIComponent(campaignId)}/sync?force=${force ? 'true' : 'false'}`,
  syncStatus: (campaignId, jobId) => `/api/campaigns/${encodeURIComponent(campaignId)}/sync/${encodeURIComponent(jobId)}`,
  sentimentPost: (campaignId, id, force = false) => `/api/campaigns/${encodeURIComponent(campaignId)}/sentiment/post/${id}${force ? '?force=true' : ''}`,
  campaignSentiment: campaignId => `/api/campaigns/${encodeURIComponent(campaignId)}/sentiment`,
  startCampaignSentiment: (campaignId, force = false) => `/api/campaigns/${encodeURIComponent(campaignId)}/sentiment?force=${force ? 'true' : 'false'}`,
  campaignSentimentStatus: (campaignId, jobId) => `/api/campaigns/${encodeURIComponent(campaignId)}/sentiment/${encodeURIComponent(jobId)}`,
  publicShare: token => `/api/share/${encodeURIComponent(token)}`,
}
