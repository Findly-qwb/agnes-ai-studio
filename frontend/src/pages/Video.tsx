import { useState, useRef, useEffect } from 'react'
import { api } from '../api/client'
import { useToast } from '../store/useToast'
import { DropZone } from '../components/DropZone'
import { useModels } from '../store/useModels'

const presets = [
  { text: 'A cinematic shot of a cat walking on the beach at sunset, golden hour lighting, waves gently rolling in, 4K quality', label: '🐱 猫咪海滩' },
  { text: 'A woman walking through a rainy Tokyo street at night, neon reflections on wet pavement, cinematic lighting', label: '🌃 东京雨夜' },
  { text: 'A drone shot flying over a misty mountain range at sunrise, clouds rolling over peaks, epic cinematic', label: '🏔 航拍山脉' },
  { text: 'Close-up of coffee being poured into a ceramic cup, steam rising, warm morning light, slow motion', label: '☕ 倾倒咖啡' },
]

export function VideoPage() {
  const toast = useToast()
  const models = useModels()
  const [prompt, setPrompt] = useState('')
  const [model, setModel] = useState('agnes-video-v2.0')
  const [resolution, setResolution] = useState('1152x768')
  const [numFrames, setNumFrames] = useState(121)
  const [frameRate, setFrameRate] = useState(24)
  const [imageUrl, setImageUrl] = useState('')
  const [previewUrl, setPreviewUrl] = useState('')
  const [negativePrompt, setNegativePrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<any>(null)
  const timerRef = useRef<number>(0)

  useEffect(() => {
    if (models?.defaults?.video_model) setModel(models.defaults.video_model)
  }, [models])

  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [])

  const startPolling = (id: string) => {
    let pollCount = 0
    timerRef.current = window.setInterval(async () => {
      pollCount++
      try {
        const data = await api.videoStatus(id)
        setStatus(data.status)
        setProgress(Math.min(pollCount * 2, 95))
        if (data.status === 'completed') {
          clearInterval(timerRef.current)
          setProgress(100)
          setResult(data)
          toast.show('视频生成完成！', 'success')
        } else if (data.status === 'failed') {
          clearInterval(timerRef.current)
          toast.show('视频生成失败', 'error')
        }
      } catch { /* ignore */ }
    }, 10000)
  }

  const generate = async () => {
    if (!prompt) { toast.show('请输入视频描述', 'error'); return }
    setLoading(true)
    setResult(null)
    setStatus('queued')
    setProgress(5)
    try {
      const [w, h] = resolution.split('x').map(Number)
      const data = await api.generateVideo({
        prompt, model, width: w, height: h,
        num_frames: numFrames, frame_rate: frameRate,
        image_url: imageUrl || undefined,
        negative_prompt: negativePrompt || undefined,
      })
      startPolling(data.task_id)
      toast.show('视频任务已提交！', 'info')
    } catch (e: any) {
      toast.show(e.message, 'error')
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  const handleFile = async (file: File) => {
    try {
      const data = await api.uploadImage(file)
      if (data.success) {
        setImageUrl(window.location.origin + data.url)
        setPreviewUrl(data.url)
      }
    } catch { toast.show('上传失败', 'error') }
  }

  const statusMap: Record<string, string> = {
    queued: '排队等待中...', in_progress: '正在生成视频，请耐心等待...',
    completed: '视频生成完成！', failed: '视频生成失败',
  }

  const playUrl = result?.video_url || (result?.local_file ? `/videos/${result.local_file}` : null)

  return (
    <div className="card">
      <div className="card-header"><span style={{ fontSize: 20 }}>🎬</span> 视频生成</div>

      <div className="presets">
        {presets.map(p => (
          <button key={p.label} className="preset-btn" onClick={() => setPrompt(p.text)}>{p.label}</button>
        ))}
      </div>

      <div className="form-group">
        <label className="form-label">视频描述</label>
        <textarea className="form-textarea" value={prompt} onChange={e => setPrompt(e.target.value)}
          placeholder="建议使用英文描述，效果更佳&#10;格式: [主体] + [动作] + [场景] + [镜头] + [光线] + [风格]" rows={4} />
      </div>

      <div className="form-group">
        <label className="form-label">参考图片 (可选 - 图生视频)</label>
        <DropZone onFile={handleFile} imageUrl={previewUrl} onRemove={() => { setImageUrl(''); setPreviewUrl('') }} />
        <input className="form-input" value={imageUrl} onChange={e => setImageUrl(e.target.value)}
          placeholder="留空则为纯文本生成视频，填入图片URL则为图生视频" style={{ marginTop: 8 }} />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label className="form-label">模型</label>
          <select className="form-select" value={model} onChange={e => setModel(e.target.value)}>
            {models && Object.entries(models.video_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">分辨率</label>
          <select className="form-select" value={resolution} onChange={e => setResolution(e.target.value)}>
            <option value="1152x768">1152×768 (默认)</option>
            <option value="1280x720">1280×720 (720p)</option>
            <option value="1920x1080">1920×1080 (1080p)</option>
            <option value="768x1344">768×1344 (9:16)</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">帧数</label>
          <select className="form-select" value={numFrames} onChange={e => setNumFrames(Number(e.target.value))}>
            <option value={81}>81 帧 (~3秒)</option>
            <option value={121}>121 帧 (~5秒)</option>
            <option value={241}>241 帧 (~10秒)</option>
            <option value={441}>441 帧 (~18秒)</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">帧率</label>
          <select className="form-select" value={frameRate} onChange={e => setFrameRate(Number(e.target.value))}>
            <option value={24}>24 fps</option><option value={30}>30 fps</option><option value={60}>60 fps</option>
          </select>
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">负面提示词 (可选)</label>
        <input className="form-input" value={negativePrompt} onChange={e => setNegativePrompt(e.target.value)}
          placeholder="blurry, low quality, distorted" />
      </div>

      <button className="btn btn-primary" onClick={generate} disabled={loading}>
        {loading ? <><span className="loading-spinner" /> 提交中...</> : '🎬 生成视频'}
      </button>

      {status && (
        <div className="result-area">
          <div className="card" style={{ background: 'var(--surface2)' }}>
            <div className="card-header">🎥 视频生成中...</div>
            <p style={{ fontSize: 13, color: 'var(--text2)' }}>{statusMap[status] || status}</p>
            <div style={{ marginTop: 12, background: 'var(--border)', borderRadius: 4, height: 4, overflow: 'hidden' }}>
              <div style={{ width: `${progress}%`, height: '100%', background: 'var(--accent)', transition: 'width 0.5s' }} />
            </div>
            {playUrl && (
              <>
                <video className="result-video" src={playUrl} controls style={{ marginTop: 16 }} />
                <div className="result-actions">
                  <button className="btn btn-sm btn-success" onClick={() => window.open(playUrl)}>▶ 播放</button>
                  <button className="btn btn-sm" onClick={() => { navigator.clipboard.writeText(playUrl); toast.show('已复制', 'success') }}>📋 复制URL</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}