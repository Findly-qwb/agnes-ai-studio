import { useState, useRef, useEffect } from 'react'
import { api } from '../api/client'
import { useToast } from '../store/useToast'
import { useModels } from '../store/useModels'

export type PromptMode = 'image' | 'img2img' | 'video'

export interface PromptConfig {
  mode: PromptMode
  prompt: string
  model: string
  size: string
  ratio?: string
  videoRatio: string
  videoSeconds: number
  fps: number
  imageUrl?: string
  translatePrompt?: boolean
}

const placeholders: Record<PromptMode, string> = {
  image: '描述你想生成的图片，例如：一只可爱的橘猫在樱花树下晒太阳，温暖治愈，摄影风格',
  img2img: '描述你想对图片做的修改，例如：把背景换成雪夜，加上霓虹灯光',
  video: '描述你想生成的视频（建议英文），例如：A cinematic shot of a cat walking on the beach at sunset',
}

export const VIDEO_RATIOS: Record<string, [number, number]> = {
  '16:9': [1280, 720], '9:16': [720, 1280], '1:1': [1024, 1024], '4:3': [1024, 768], '3:4': [768, 1024],
}

// Agnes Video V2.0 旧协议要求 num_frames ≤441 且遵循 8n+1；按秒数换算成最近合规帧数
export const secondsToFrames = (seconds: number, fps: number) =>
  Math.min(Math.max(Math.round(seconds * fps / 8) * 8 + 1, 9), 441)

// 2.1 模型走档位尺寸（1K-4K）+ 宽高比；2.0 模型只支持精确像素尺寸
const TIER_SIZES = ['1K', '2K', '3K', '4K']
const IMAGE_RATIOS = ['1:1', '4:3', '3:4', '16:9', '9:16', '3:2', '2:3', '21:9']
// 支持 1K/2K 档位 + ratio 的 Agnes 图像模型（2.5 与 2.1 请求参数完全一致）
const TIERED_IMAGE_MODELS = new Set(['agnes-image-2.1-flash', 'agnes-image-2.5-flash'])

interface Props {
  busy?: boolean
  onSubmit: (config: PromptConfig) => void
}

export function PromptInput({ busy, onSubmit }: Props) {
  const toast = useToast()
  const models = useModels()
  const [mode, setMode] = useState<PromptMode>('image')
  const [prompt, setPrompt] = useState('')
  const [size, setSize] = useState('1K')
  const [legacySize, setLegacySize] = useState('1024x1024')
  const [ratio, setRatio] = useState('1:1')
  const [imageModel, setImageModel] = useState('')
  const [videoModel, setVideoModel] = useState('')
  const [videoRatio, setVideoRatio] = useState('16:9')
  const [videoSeconds, setVideoSeconds] = useState(5)
  const [fps, setFps] = useState(24)
  const [attach, setAttach] = useState<{ preview: string; url: string } | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [enhancing, setEnhancing] = useState(false)
  const [translateOn, setTranslateOn] = useState(true)
  const [enhanced, setEnhanced] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const needsImage = mode !== 'image'
  const model = mode === 'video' ? videoModel : imageModel
  const modelOptions = mode === 'video' ? models?.video_models : models?.image_models
  const modelDefault = mode === 'video'
    ? (models?.defaults?.video_model || 'agnes-video-2.5-flash')
    : (models?.defaults?.image_model || 'agnes-image-2.5-flash')

  useEffect(() => {
    if (models) {
      setImageModel(models.defaults?.image_model || 'agnes-image-2.5-flash')
      setVideoModel(models.defaults?.video_model || 'agnes-video-2.5-flash')
    }
  }, [models])

  const uploadFile = async (file: File) => {
    if (!file.type.startsWith('image/')) { toast.show('请选择图片文件', 'error'); return }
    try {
      const data = await api.uploadImage(file)
      if (data.success) {
        setAttach({ preview: data.url, url: window.location.origin + data.url })
        // 有参考图就按图生图走，否则用户容易停留在"图片生成"导致参考图被忽略
        setMode(m => m === 'image' ? 'img2img' : m)
      }
    } catch { toast.show('上传失败', 'error') }
  }

  const enhance = async () => {
    if (!prompt.trim()) { toast.show('请先输入描述再优化', 'error'); return }
    setEnhancing(true)
    try {
      const d = await api.enhancePrompt({ prompt, mode })
      if (d.success) { setEnhanced(d.enhanced) } else { toast.show(d.error || '优化失败', 'error') }
    } catch (e: any) {
      toast.show(e.message, 'error')
    } finally {
      setEnhancing(false)
    }
  }

  const submit = () => {
    if (!prompt.trim()) { toast.show('请输入描述', 'error'); return }
    if (mode === 'img2img' && !attach) { toast.show('图生图需要先上传参考图', 'error'); return }
    const tiered = TIERED_IMAGE_MODELS.has(model || modelDefault)
    onSubmit({
      mode, prompt, model: model || modelDefault,
      size: mode === 'video' || tiered ? size : legacySize,
      ratio: mode !== 'video' && tiered ? ratio : undefined,
      videoRatio, videoSeconds, fps, imageUrl: attach?.url,
      translatePrompt: translateOn,
    })
  }

  return (
    <div className={`composer ${dragOver ? 'drag-over' : ''}`}
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) uploadFile(f) }}>
      <div className="composer-top">
        <button className={`attach-btn ${needsImage && !attach ? 'required' : ''}`} onClick={() => fileRef.current?.click()}>
          ＋ 参考图{needsImage ? '（必选）' : '（可选）'}
        </button>
        {attach && (
          <div className="attachments">
            <div className="attach-chip">
              <img src={attach.preview} alt="" />
              <button onClick={() => setAttach(null)}>✕</button>
            </div>
          </div>
        )}
      </div>

      <textarea className="composer-input" value={prompt}
        onChange={e => setPrompt(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
        placeholder={placeholders[mode]} />

      {enhanced && (
        <div className="enhance-bar">
          <div className="enhance-text">{enhanced}</div>
          <div className="enhance-actions">
            <button className="btn btn-sm btn-primary" onClick={() => { setPrompt(enhanced); setEnhanced(null); toast.show('已采用优化结果', 'success') }}>采用</button>
            <button className="btn btn-sm" onClick={() => setEnhanced(null)}>放弃</button>
          </div>
        </div>
      )}

      <div className="composer-footer">
        <div className="composer-footer-left">
          <select className="composer-size" value={mode} onChange={e => { setMode(e.target.value as PromptMode); if (e.target.value === 'image') setAttach(null) }}>
            <option value="image">🖼 图片生成</option>
            <option value="img2img">🎨 图生图</option>
            <option value="video">🎬 视频生成</option>
          </select>
          <select className="composer-size" value={model || modelDefault} onChange={e => mode === 'video' ? setVideoModel(e.target.value) : setImageModel(e.target.value)}>
            {Object.entries(modelOptions || {}).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        {mode !== 'video' ? (
          <>
          {TIERED_IMAGE_MODELS.has(model || modelDefault) ? (
              <>
                <select className="composer-size" value={size} onChange={e => setSize(e.target.value)} title="分辨率档位">
                  {TIER_SIZES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <select className="composer-size" value={ratio} onChange={e => setRatio(e.target.value)} title="宽高比">
                  {IMAGE_RATIOS.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </>
            ) : (
              <select className="composer-size" value={legacySize} onChange={e => setLegacySize(e.target.value)} title="输出尺寸">
                <option value="1024x1024">1:1 · 1024x1024</option>
                <option value="1024x768">4:3 · 1024x768</option>
                <option value="768x1024">3:4 · 768x1024</option>
                <option value="1536x1024">16:9 · 1536x1024</option>
                <option value="1024x1536">9:16 · 1024x1536</option>
              </select>
            )}
            <button type="button" className={`composer-size translate-toggle${translateOn ? ' on' : ''}`}
              onClick={() => setTranslateOn(v => !v)}
              title="中文描述自动翻译成英文后再生成（Agnes 图像模型对英文的理解更准）">
              🌐→EN
            </button>
          </>
          ) : (
            <>
              <select className="composer-size" value={videoRatio} onChange={e => setVideoRatio(e.target.value)}>
                {Object.keys(VIDEO_RATIOS).map(r => <option key={r} value={r}>{r}</option>)}
              </select>
              <select className="composer-size" value={videoSeconds} onChange={e => setVideoSeconds(+e.target.value)}>
                {[3, 5, 10].map(s => <option key={s} value={s}>{s}s</option>)}
              </select>
              <select className="composer-size" value={fps} onChange={e => setFps(+e.target.value)}>
                {[16, 24, 30].map(f => <option key={f} value={f}>{f}fps</option>)}
              </select>
            </>
          )}
        </div>
        <div className="composer-footer-right">
          <button className="wand-btn" onClick={enhance} disabled={enhancing} title="提示词优化">
            {enhancing ? <span className="loading-spinner" /> : '🪄'}
          </button>
          <button className="send-btn" onClick={submit} disabled={busy}>
            {busy ? <span className="loading-spinner" /> : '↑'}
          </button></div>
        <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={e => {
          if (e.target.files?.[0]) uploadFile(e.target.files[0])
          e.target.value = ''
        }} />
      </div>
    </div>
  )
}
