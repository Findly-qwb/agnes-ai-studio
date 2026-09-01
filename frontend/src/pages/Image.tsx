import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { useToast } from '../store/useToast'
import { useModels } from '../store/useModels'

const presets = [
  { text: '一只可爱的橘猫在樱花树下晒太阳，温暖的阳光洒在它身上，画面温暖治愈，摄影风格', label: '🐱 橘猫樱花' },
  { text: '一座未来主义城市，高耸的玻璃建筑，飞行汽车在空中穿梭，赛博朋克风格，霓虹灯光，夜晚', label: '🏙 赛博都市' },
  { text: '一杯精致的咖啡放在木桌上，旁边有一本书，窗外是雨天的街道，温馨舒适的氛围，电影感', label: '☕ 咖啡时光' },
  { text: '梦幻般的森林仙境，萤火虫飞舞，古老的树木，柔和的光线透过树叶，奇幻风格，魔法氛围', label: '✨ 魔法森林' },
]

export function ImagePage() {
  const toast = useToast()
  const models = useModels()
  const [prompt, setPrompt] = useState('')
  const [model, setModel] = useState('agnes-image-2.5-flash')
  const [size, setSize] = useState('1024x1024')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)

  useEffect(() => {
    if (models?.defaults?.image_model) setModel(models.defaults.image_model)
  }, [models])

  const generate = async () => {
    if (!prompt) { toast.show('请输入图片描述', 'error'); return }
    setLoading(true)
    try {
      const data = await api.generateImage({ prompt, model, size })
      setResult(data)
      toast.show('图片生成成功！', 'success')
    } catch (e: any) {
      toast.show(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <div className="card-header"><span style={{ fontSize: 20 }}>🖼</span> 文生图</div>

      <div className="presets">
        {presets.map(p => (
          <button key={p.label} className="preset-btn" onClick={() => setPrompt(p.text)}>{p.label}</button>
        ))}
      </div>

      <div className="form-group">
        <label className="form-label">图片描述</label>
        <textarea className="form-textarea" value={prompt} onChange={e => setPrompt(e.target.value)}
          placeholder="描述你想要生成的图片..." rows={4} />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label className="form-label">模型</label>
          <select className="form-select" value={model} onChange={e => setModel(e.target.value)}>
            {models && Object.entries(models.image_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">尺寸</label>
          <select className="form-select" value={size} onChange={e => setSize(e.target.value)}>
            <option value="1024x1024">1024×1024 (正方形)</option>
            <option value="1024x768">1024×768 (横版)</option>
            <option value="768x1024">768×1024 (竖版)</option>
            <option value="1536x1024">1536×1024 (宽屏)</option>
          </select>
        </div>
      </div>

      <button className="btn btn-primary" onClick={generate} disabled={loading}>
        {loading ? <><span className="loading-spinner" /> 生成中...</> : '✨ 生成图片'}
      </button>

      {result && (
        <div className="result-area">
          <img className="result-image" src={result.image_url} alt="" />
          <div className="result-actions">
            <button className="btn btn-sm" onClick={() => window.open(result.image_url)}>📥 下载</button>
            <button className="btn btn-sm" onClick={() => {
              navigator.clipboard.writeText(result.image_url)
              toast.show('已复制', 'success')
            }}>📋 复制URL</button>
            {result.local_file && <span style={{ fontSize: 11, color: 'var(--success)' }}>✅ 已保存到 pictures/{result.local_file}</span>}
          </div>
        </div>
      )}
    </div>
  )
}