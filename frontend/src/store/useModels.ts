import { useEffect, useState } from 'react'
import { api } from '../api/client'

interface ModelData {
  text_models: Record<string, string>
  image_models: Record<string, string>
  video_models: Record<string, string>
  defaults: { text_model: string; image_model: string; video_model: string }
}

export function useModels() {
  const [models, setModels] = useState<ModelData | null>(null)

  useEffect(() => {
    api.dramaModels().then(d => {
      if (d.success) setModels(d)
    }).catch(() => {})
  }, [])

  return models
}