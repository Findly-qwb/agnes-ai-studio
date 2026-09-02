import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { useToast } from '../store/useToast'
import { Modal } from '../components/Modal'

interface SettingsProps {
  show: boolean
  onClose: () => void
}

export function Settings({ show, onClose }: SettingsProps) {
  const toast = useToast()
  const [apiKey, setApiKey] = useState('')
  const [deepseekKey, setDeepseekKey] = useState('')
  const [doubaoKey, setDoubaoKey] = useState('')
  const [qwenKey, setQwenKey] = useState('')
  const [minimaxKey, setMinimaxKey] = useState('')
  const [ollamaEnabled, setOllamaEnabled] = useState(false)
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434')
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [ollamaDetected, setOllamaDetected] = useState<string[]>([])
  const [customModels, setCustomModels] = useState<any[]>([])
  const [showAddForm, setShowAddForm] = useState(false)
  const [newModel, setNewModel] = useState({ id: '', name: '', type: 'text', baseUrl: '', apiKey: '' })
  const [loading, setLoading] = useState(false)
  const [textModelOptions, setTextModelOptions] = useState<Record<string, string>>({})
  const [enhanceModel, setEnhanceModel] = useState('agnes-2.5-flash')

  useEffect(() => {
    if (!show) return
    api.getConfig().then(d => {
      if (d.api_key_masked) setApiKey('')
      if (d.deepseek_api_key_masked) setDeepseekKey('')
      if (d.doubao_api_key_masked) setDoubaoKey('')
      if (d.qwen_api_key_masked) setQwenKey('')
      if (d.minimax_api_key_masked) setMinimaxKey('')
      if (d.prompt_enhance_model) setEnhanceModel(d.prompt_enhance_model)
    }).catch(() => { })
    // /api/drama/models 才是合并了自定义模型（且过滤掉无 Key）的全量文本模型；
    // anchorModels 只有内置选项，用它会导致自定义模型不显示
    api.dramaModels().then(d => {
      if (d.success) setTextModelOptions(d.text_models || {})
    }).catch(() => { })
    api.ollamaConfig().then(d => {
      if (d.success) {
        setOllamaEnabled(d.config.enabled)
        setOllamaUrl(d.config.base_url)
        setOllamaModels(d.config.models || [])
      }
    }).catch(() => { })
    loadCustomModels()
  }, [show])

  const loadCustomModels = async () => {
    try {
      const d = await api.listCustomModels()
      setCustomModels(d.models || [])
    } catch { /* ignore */ }
  }

  const handleSave = async () => {
    setLoading(true)
    try {
      const payload: any = {}
      if (apiKey) payload.api_key = apiKey
      if (deepseekKey) payload.deepseek_api_key = deepseekKey
      if (doubaoKey) payload.doubao_api_key = doubaoKey
      if (qwenKey) payload.qwen_api_key = qwenKey
      if (minimaxKey) payload.minimax_api_key = minimaxKey
      if (enhanceModel) payload.prompt_enhance_model = enhanceModel
      if (Object.keys(payload).length > 0) {
        await api.saveConfig(payload)
      }
      await api.saveOllamaConfig({ enabled: ollamaEnabled, base_url: ollamaUrl, models: ollamaModels })
      toast.show('配置已保存', 'success')
      onClose()
    } catch (e: any) {
      toast.show('保存失败: ' + e.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleDetect = async () => {
    try {
      const d = await api.ollamaDetect(ollamaUrl)
      if (d.success) {
        setOllamaDetected(d.models)
        setOllamaModels(d.models)
        toast.show(`检测到 ${d.models.length} 个模型`, 'success')
      } else {
        toast.show(d.error || '检测失败', 'error')
      }
    } catch { toast.show('检测失败', 'error') }
  }

  const handleAddCustom = async () => {
    if (!newModel.id || !newModel.name || !newModel.baseUrl) {
      toast.show('请填写完整信息', 'error'); return
    }
    try {
      const d = await api.addCustomModel({
        model_id: newModel.id, display_name: newModel.name,
        model_type: newModel.type, base_url: newModel.baseUrl, api_key: newModel.apiKey,
      })
      if (d.success) {
        toast.show('添加成功', 'success')
        setShowAddForm(false)
        setNewModel({ id: '', name: '', type: 'text', baseUrl: '', apiKey: '' })
        loadCustomModels()
      } else {
        toast.show(d.error || '添加失败', 'error')
      }
    } catch { toast.show('添加失败', 'error') }
  }

  const handleDeleteCustom = async (id: string) => {
    try {
      await api.deleteCustomModel(id)
      loadCustomModels()
      toast.show('已删除', 'success')
    } catch { toast.show('删除失败', 'error') }
  }

  const typeLabels: Record<string, string> = { text: '📝文本', image: '🖼生图', video: '🎬视频' }

  return (
    <Modal show={show} title="⚙ API 设置" onClose={onClose} maxWidth={520}
      actions={
        <>
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={loading}>
            {loading ? '保存中...' : '💾 保存'}
          </button>
        </>
      }>
      <div style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 12 }}>各厂商可独立配置 API Key，未填写的厂商将使用全局 Agnes AI Key</div>

      <div className="form-group">
        <label className="form-label">🔑 Agnes AI API Key（全局）</label>
        <input className="form-input" type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="sk-..." />
      </div>

      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '12px 0' }} />
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>📝 文本模型</div>
      <div className="form-group">
        <label className="form-label">DeepSeek API Key</label>
        <input className="form-input" type="password" value={deepseekKey} onChange={e => setDeepseekKey(e.target.value)} placeholder="DeepSeek API Key（可选）" />
      </div>
      <div className="form-group">
        <label className="form-label">豆包（火山引擎）API Key</label>
        <input className="form-input" type="password" value={doubaoKey} onChange={e => setDoubaoKey(e.target.value)} placeholder="豆包 API Key（可选）" />
      </div>
      <div className="form-group">
        <label className="form-label">通义千问（DashScope）API Key</label>
        <input className="form-input" type="password" value={qwenKey} onChange={e => setQwenKey(e.target.value)} placeholder="DashScope API Key（可选）" />
      </div>

      <div className="form-group">
        <label className="form-label">🪄 提示词优化模型</label>
        <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 6 }}>PromptInput 里 🪄 魔法棒按钮用来扩写提示词所使用的文本模型</div>
        <select className="form-select" value={enhanceModel} onChange={e => setEnhanceModel(e.target.value)}>
          {Object.entries(textModelOptions).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
        </select>
      </div>

      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '12px 0' }} />
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>🖼 生图模型</div>
      <div className="form-group">
        <label className="form-label">MiniMax API Key</label>
        <input className="form-input" type="password" value={minimaxKey} onChange={e => setMinimaxKey(e.target.value)} placeholder="MiniMax API Key（可选）" />
      </div>

      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '12px 0' }} />
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>🦙 Ollama 本地模型</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, cursor: 'pointer' }}>
          <input type="checkbox" checked={ollamaEnabled} onChange={e => setOllamaEnabled(e.target.checked)} />
          启用 Ollama
        </label>
        <input className="form-input" value={ollamaUrl} onChange={e => setOllamaUrl(e.target.value)} style={{ fontSize: 11, flex: 1 }} disabled={!ollamaEnabled} />
        <button className="btn btn-sm" onClick={handleDetect} disabled={!ollamaEnabled}>🔍 检测模型</button>
      </div>
      {ollamaDetected.length > 0 && (
        <div style={{ fontSize: 11, color: 'var(--success)', marginBottom: 4 }}>
          ✅ 检测到 {ollamaDetected.length} 个模型: {ollamaDetected.join(', ')}
        </div>
      )}

      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '12px 0' }} />
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>🔧 自定义模型</div>
      <div style={{ marginBottom: 8 }}>
        {customModels.map(m => (
          <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 8px', background: 'var(--surface2)', borderRadius: 4, marginBottom: 4, fontSize: 11 }}>
            <span><b>{m.name}</b> <span style={{ color: 'var(--text2)' }}>[{typeLabels[m.type] || m.type}]</span></span>
            <button onClick={() => handleDeleteCustom(m.id)} style={{ color: 'var(--error)', background: 'none', border: 'none', cursor: 'pointer', fontSize: 12 }}>✖</button>
          </div>
        ))}
      </div>

      {showAddForm ? (
        <div style={{ background: 'var(--surface2)', padding: 10, borderRadius: 8, marginBottom: 8 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            <input className="form-input" placeholder="模型 ID" style={{ fontSize: 11 }} value={newModel.id} onChange={e => setNewModel(p => ({ ...p, id: e.target.value }))} />
            <input className="form-input" placeholder="显示名称" style={{ fontSize: 11 }} value={newModel.name} onChange={e => setNewModel(p => ({ ...p, name: e.target.value }))} />
            <select className="form-input" style={{ fontSize: 11 }} value={newModel.type} onChange={e => setNewModel(p => ({ ...p, type: e.target.value }))}>
              <option value="text">文本模型</option>
              <option value="image">生图模型</option>
              <option value="video">生视频模型</option>
            </select>
            <input className="form-input" placeholder="API 地址" style={{ fontSize: 11 }} value={newModel.baseUrl} onChange={e => setNewModel(p => ({ ...p, baseUrl: e.target.value }))} />
          </div>
          <input className="form-input" placeholder="API Key（可选）" style={{ fontSize: 11, marginTop: 6 }} value={newModel.apiKey} onChange={e => setNewModel(p => ({ ...p, apiKey: e.target.value }))} />
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <button className="btn btn-sm btn-primary" onClick={handleAddCustom}>✅ 保存</button>
            <button className="btn btn-sm" onClick={() => setShowAddForm(false)}>取消</button>
          </div>
        </div>
      ) : (
        <button className="btn btn-sm" onClick={() => setShowAddForm(true)}>➕ 添加自定义模型</button>
      )}
    </Modal>
  )
}