// 提示词一键优化：🪄 → 预览 → 采用/放弃。复用 /api/prompt/enhance，不碰宿主 textarea 的受控状态
import { useState } from 'react'
import { api } from '../api/client'
import { useToast } from '../store/useToast'

export function EnhanceBtn({ getText, mode, onApply }: {
  getText: () => string, mode: string, onApply: (t: string) => void
}) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [enh, setEnh] = useState<string | null>(null)
  const run = async () => {
    const text = (getText() || '').trim()
    if (!text) { toast.show('请先输入描述再优化', 'error'); return }
    setBusy(true)
    try {
      const d = await api.enhancePrompt({ prompt: text, mode })
      if (d.success) setEnh(d.enhanced)
      else toast.show(d.error || '优化失败', 'error')
    } catch (e: any) { toast.show(e.message, 'error') }
    finally { setBusy(false) }
  }
  return (
    <>
      <button type="button" className="wand-btn" onClick={run} disabled={busy} title="提示词优化（🪄）">
        {busy ? <span className="loading-spinner" /> : '🪄'}
      </button>
      {enh && (
        <div className="enhance-bar">
          <div className="enhance-text">{enh}</div>
          <div className="enhance-actions">
            <button type="button" className="btn btn-sm btn-primary" onClick={() => { onApply(enh); setEnh(null); toast.show('已采用优化结果', 'success') }}>采用</button>
            <button type="button" className="btn btn-sm" onClick={() => setEnh(null)}>放弃</button>
          </div>
        </div>
      )}
    </>
  )
}
