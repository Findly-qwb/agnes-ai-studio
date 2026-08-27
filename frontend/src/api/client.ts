// ponytail: 生产构建由 Flask 同端口托管，直接用当前 origin；dev 模式仍指向固定 5001
const API_BASE = import.meta.env.DEV ? 'http://127.0.0.1:5001' : window.location.origin

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}

export const api = {
  // Config
  getConfig: () => req<any>('/api/config'),
  saveConfig: (body: any) => req<any>('/api/config', { method: 'POST', body: JSON.stringify(body) }),
  enhancePrompt: (body: { prompt: string; mode: string }) =>
    req<any>('/api/prompt/enhance', { method: 'POST', body: JSON.stringify(body) }),

  // Image
  generateImage: (body: { prompt: string; model?: string; size?: string; ratio?: string; save_local?: boolean }) =>
    req<any>('/api/image/generate', { method: 'POST', body: JSON.stringify(body) }),
  img2img: (body: { prompt: string; image_url: string; size?: string; ratio?: string; model?: string }) =>
    req<any>('/api/image/img2img', { method: 'POST', body: JSON.stringify(body) }),
  uploadImage: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${API_BASE}/api/upload/image`, { method: 'POST', body: fd }).then(r => r.json())
  },

  // Video
  generateVideo: (body: any) => req<any>('/api/video/generate', { method: 'POST', body: JSON.stringify(body) }),
  videoStatus: (taskId: string) => req<any>(`/api/video/status/${taskId}`),
  listVideoTasks: () => req<any>('/api/video/tasks'),

  // Drama
  startDrama: (body: any) => req<any>('/api/drama/start', { method: 'POST', body: JSON.stringify(body) }),
  stopDrama: (dramaId: string) => req<any>('/api/drama/stop', { method: 'POST', body: JSON.stringify({ drama_id: dramaId }) }),
  dramaStatus: (dramaId: string) => req<any>(`/api/drama/status/${dramaId}`),
  dramaModels: () => req<any>('/api/drama/models'),
  dramaResume: (dramaId: string) => req<any>('/api/drama/resume', { method: 'POST', body: JSON.stringify({ drama_id: dramaId }) }),
  storyConfirm: (dramaId: string, edited_story?: string) =>
    req<any>('/api/drama/story/confirm', { method: 'POST', body: JSON.stringify({ drama_id: dramaId, edited_story }) }),
  mergeCustom: (body: any) => req<any>('/api/drama/merge/custom', { method: 'POST', body: JSON.stringify(body) }),
  shotRegenerate: (body: any) => req<any>('/api/drama/shot/regenerate', { method: 'POST', body: JSON.stringify(body) }),
  assetReplace: (dramaId: string, assetIndex: number, file: File) => {
    const fd = new FormData()
    fd.append('drama_id', dramaId)
    fd.append('asset_index', String(assetIndex))
    fd.append('file', file)
    return fetch(`${API_BASE}/api/drama/asset/replace`, { method: 'POST', body: fd }).then(r => r.json())
  },
  assetRegenerate: (body: any) => req<any>('/api/drama/asset/regenerate', { method: 'POST', body: JSON.stringify(body) }),
  shotUploadImage: (dramaId: string, shotIndex: number, file: File) => {
    const fd = new FormData()
    fd.append('drama_id', dramaId)
    fd.append('shot_index', String(shotIndex))
    fd.append('file', file)
    return fetch(`${API_BASE}/api/drama/shot/upload_image`, { method: 'POST', body: fd }).then(r => r.json())
  },
  shotDeleteImage: (body: any) => req<any>('/api/drama/shot/delete_image', { method: 'POST', body: JSON.stringify(body) }),

  // Anchor
  anchorModels: () => req<any>('/api/anchor/models'),
  anchorVoices: () => req<any>('/api/anchor/voices'),
  anchorUpload: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${API_BASE}/api/anchor/upload`, { method: 'POST', body: fd }).then(r => r.json())
  },
  anchorGenerate: (body: any) => req<any>('/api/anchor/generate', { method: 'POST', body: JSON.stringify(body) }),
  anchorStatus: (taskId?: string) => req<any>(`/api/anchor/status${taskId ? `?task_id=${taskId}` : ''}`),

  // Files
  listFiles: (subdir: string) => req<any>(`/api/files/${subdir}`),
  shutdown: () => req<any>('/api/shutdown', { method: 'POST' }),

  // Ollama
  ollamaConfig: () => req<any>('/api/ollama/config'),
  saveOllamaConfig: (body: any) => req<any>('/api/ollama/config', { method: 'POST', body: JSON.stringify(body) }),
  ollamaDetect: (baseUrl: string) => req<any>('/api/ollama/detect', { method: 'POST', body: JSON.stringify({ base_url: baseUrl }) }),

  // Custom models
  listCustomModels: () => req<any>('/api/custom-models'),
  addCustomModel: (body: any) => req<any>('/api/custom-models', { method: 'POST', body: JSON.stringify(body) }),
  deleteCustomModel: (modelId: string) => req<any>('/api/custom-models', { method: 'DELETE', body: JSON.stringify({ model_id: modelId }) }),
}