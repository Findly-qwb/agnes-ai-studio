import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { useToast } from '../store/useToast'
import { DropZone } from '../components/DropZone'
import { useModels } from '../store/useModels'

const presets = [
  { label: '🏠 家居摆件', text: '将这张商品图片放置在大理石台面上，背景为简约现代风格，柔和的自然光从左侧照射，营造高端质感的产品宣传图，4K高清，商业摄影风格' },
  { label: '💄 美妆护肤', text: '将这张化妆品产品图放置在鲜花和绿叶环绕的大理石台面上，背景为柔和的粉色渐变，光线柔和通透，营造清新自然的美妆广告风格，高清商业摄影' },
  { label: '🍽 美食餐饮', text: '将这张食品图片放置在木质餐盘上，周围点缀新鲜食材和香料，背景为暖色调的厨房场景，自然光照射，营造食欲满满的美食宣传图，高清摄影风格' },
  { label: '📱 数码产品', text: '将这张数码产品图片放置在简约白色桌面上，背景为科技感渐变蓝色光影，光线干净利落，营造现代科技产品宣传图风格，4K高清商业摄影' },
  { label: '👗 服装鞋帽', text: '将这张服装图片展示在时尚都市街头，背景为模糊的城市建筑，阳光自然照射，营造时尚品牌宣传图风格，高清摄影' },
  { label: '💎 珠宝奢侈品', text: '将这张珠宝首饰图片放置在黑色丝绒展示台上，背景为深色奢华风格，点缀光影效果，营造高端珠宝广告风格，高清微距摄影' },
  { label: '🍼 母婴用品', text: '将这张母婴产品图片放置在温馨明亮的婴儿房场景中，周围有柔软的毛毯和可爱玩具，光线柔和温暖，营造安全温馨的宣传图风格，高清摄影' },
  { label: '🛒 电商主图', text: '将这张图片制作成电商主图风格，纯白背景，产品居中，四周留白均匀，光线均匀无阴影，突出产品本身细节，适合淘宝京东等电商平台使用' },
]

export function Img2ImgPage() {
  const toast = useToast()
  const models = useModels()
  const [prompt, setPrompt] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const [size, setSize] = useState('1024x1024')
  const [model, setModel] = useState('agnes-image-2.1-flash')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [previewUrl, setPreviewUrl] = useState('')

  useEffect(() => {
    if (models?.defaults?.image_model) setModel(models.defaults.image_model)
  }, [models])

  const handleFile = async (file: File) => {
    try {
      const data = await api.uploadImage(file)
      if (data.success) {
        const url = window.location.origin + data.url
        setImageUrl(url)
        setPreviewUrl(data.url)
      }
    } catch { toast.show('上传失败', 'error') }
  }

  const generate = async () => {
    if (!prompt || !imageUrl) { toast.show('请输入描述和图片', 'error'); return }
    setLoading(true)
    try {
      const data = await api.img2img({ prompt, image_url: imageUrl, size, model })
      setResult(data)
      toast.show('图片编辑成功！', 'success')
    } catch (e: any) {
      toast.show(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <div className="card-header"><span style={{ fontSize: 20 }}>🎨</span> 图生图</div>

      <div className="form-group">
        <label className="form-label">参考图片</label>
        <DropZone onFile={handleFile} imageUrl={previewUrl} onRemove={() => { setImageUrl(''); setPreviewUrl('') }} />
        <div className="form-hint" style={{ marginTop: 8 }}>或者直接输入图片 URL：</div>
        <input className="form-input" value={imageUrl} onChange={e => setImageUrl(e.target.value)} placeholder="输入参考图片的 URL 地址..." style={{ marginTop: 4 }} />
      </div>

      <div className="form-group">
        <label className="form-label">编辑描述</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
          {presets.map(p => (
            <button key={p.label} className="preset-btn" onClick={() => setPrompt(p.text)} style={{ fontSize: 11, padding: '4px 10px' }}>{p.label}</button>
          ))}
        </div>
        <textarea className="form-textarea" value={prompt} onChange={e => setPrompt(e.target.value)}
          placeholder="描述你希望对参考图片做什么修改..." rows={4} />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label className="form-label">尺寸</label>
          <select className="form-select" value={size} onChange={e => setSize(e.target.value)}>
            <option value="1024x1024">1:1 (1024×1024)</option>
            <option value="1344x768">16:9 (1344×768)</option>
            <option value="768x1344">9:16 (768×1344)</option>
            <option value="1024x768">4:3 (1024×768)</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">生图模型</label>
          <select className="form-select" value={model} onChange={e => setModel(e.target.value)}>
            {models && Object.entries(models.image_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
        </div>
      </div>

      <button className="btn btn-primary" onClick={generate} disabled={loading}>
        {loading ? <><span className="loading-spinner" /> 编辑中...</> : '🎨 开始编辑'}
      </button>

      {result && (
        <div className="result-area">
          <img className="result-image" src={result.image_url} alt="" />
          <div className="result-actions">
            <button className="btn btn-sm" onClick={() => window.open(result.image_url)}>📥 下载</button>
            <button className="btn btn-sm" onClick={() => { navigator.clipboard.writeText(result.image_url); toast.show('已复制', 'success') }}>📋 复制URL</button>
          </div>
        </div>
      )}
    </div>
  )
}