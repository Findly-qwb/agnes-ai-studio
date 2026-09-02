// 画布自定义节点卡片（Krea/ComfyUI 式：卡片即编辑器 + 选中浮动操作条）
import { type CSSProperties, useState } from 'react'
import { Handle, Position, NodeToolbar, type NodeProps } from '@xyflow/react'
import { api } from '../../api/client'

export type Chip = {
  key: string
  label: string
  value: string
  inherited?: string
  options: [string, string][]
}

export type Preview = { type: 'img' | 'video', src: string }

export type FlowNodeData = {
  nodeType: string
  label: string
  status: string
  error: string
  summary: string
  previews: Preview[]
  text?: string
  editable?: boolean
  chips: Chip[]
  flowId: string
  nodeParams: Record<string, unknown>
  onChanged?: () => void
  onRun?: (id: string) => void
  onRunDown?: (id: string) => void
  onDelete?: (id: string) => void
  onOpen?: (id: string) => void
  onZoom?: (p: Preview) => void
  onSaveText?: (id: string, text: string) => Promise<void>
  [key: string]: unknown
}

export const STATUS_COLORS: Record<string, string> = {
  pending: '#b9bfd4', running: '#3b82f6', completed: 'var(--success)',
  failed: 'var(--error)', stale: '#f59e0b', stopped: '#b9bfd4',
  interrupted: '#f59e0b',
}
export const TYPE_COLORS: Record<string, string> = {
  prompt: '#5b5bd6', story: '#8b5cf6', script: '#06b6d4', storyboard: '#f59e0b',
  assets: '#ec4899', shots: '#22c55e', merge: '#64748b',
}
const STATUS_LABELS: Record<string, string> = {
  pending: '待运行', running: '运行中…', completed: '完成', failed: '失败',
  stale: '需重跑', stopped: '已停止', interrupted: '已中断',
}

// ComfyUI 式内联 widget：点 chip 直接在卡片上换模型/时长/风格
function ChipSelect({ chip, flowId, nodeId, nodeParams, onSaved }: {
  chip: Chip, flowId: string, nodeId: string, nodeParams: Record<string, unknown>, onSaved?: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(chip.value)
  const display = chip.options.find(([k]) => k === val)?.[1] || val
  if (editing) {
    return (
      <select className="flow-chip-select" autoFocus value={val}
        onPointerDown={e => e.stopPropagation()}
        onBlur={() => setEditing(false)}
        onChange={async e => {
          const v = e.target.value
          setVal(v)
          setEditing(false)
          const merged = { ...nodeParams, [chip.key]: v }
          // 只有等于「继承值」才算冗余可删；等于当前生效值(可能是旧 override)不能删，否则静默回退旧模型
          if (v === (chip.inherited ?? '')) delete merged[chip.key]
          try { await api.flowNodeParams(flowId, nodeId, merged); onSaved?.() } catch { }
        }}>
        {chip.options.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
      </select>
    )
  }
  return (
    <span title={`${chip.label}（点击修改）`}
      onClick={e => { e.stopPropagation(); setEditing(true) }}
      onPointerDown={e => e.stopPropagation()}>
      {chip.label}·{display.length > 14 ? display.slice(0, 13) + '…' : display}
    </span>
  )
}

// 文本类节点（描述/故事/剧本）就地编辑：双击进编辑，不用开抽屉
function InlineText({ d, nodeId }: { d: FlowNodeData, nodeId: string }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(d.text || '')
  if (editing) {
    return (
      <div className="nodrag" style={{ marginTop: 6 }} onDoubleClick={e => e.stopPropagation()}>
        <textarea autoFocus value={text} onChange={e => setText(e.target.value)}
          onKeyDown={e => e.stopPropagation()}
          style={{ width: '100%', minHeight: 110, fontSize: 12, lineHeight: 1.6, background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--accent)', borderRadius: 6, padding: 6, fontFamily: 'inherit', resize: 'vertical' }} />
        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', marginTop: 4 }}>
          <button className="flow-mini-btn" onClick={() => { setEditing(false); setText(d.text || '') }}>取消</button>
          <button className="flow-mini-btn primary" onClick={async () => {
            setEditing(false)
            await d.onSaveText?.(nodeId, text)
            d.onChanged?.()
          }}>💾 保存</button>
        </div>
      </div>
    )
  }
  return (
    <div className="flow-node-text" title="双击就地编辑"
      onDoubleClick={e => { e.stopPropagation(); setEditing(true) }}>
      {d.text || '暂无内容：选中节点后点「▶ 运行」生成'}
    </div>
  )
}

export function FlowNodeCard({ data, selected, id }: NodeProps) {
  const d = data as unknown as FlowNodeData
  return (
    <div className={`flow-node${selected ? ' selected' : ''}`}
      style={{ '--type-color': TYPE_COLORS[d.nodeType] || 'var(--accent)' } as CSSProperties}>
      <NodeToolbar position={Position.Top} className="flow-toolbar nodrag">
        <button onClick={() => d.onRun?.(id)} title="运行此节点（未完成的祖先自动补齐）">▶ 运行</button>
        <button onClick={() => d.onRunDown?.(id)} title="运行此节点及全部下游">⏩ 下游</button>
        <button onClick={() => d.onOpen?.(id)} title="打开右侧详情面板">✎ 详情</button>
        <button className="danger" onClick={() => d.onDelete?.(id)} title="删除节点">🗑</button>
      </NodeToolbar>
      <span className="flow-node-bar" />
      <div className="flow-node-body">
        <div className="flow-node-head">
          <b>{d.label}</b>
          <span className={`flow-dot ${d.status}`} title={STATUS_LABELS[d.status] || d.status} />
        </div>
        {d.error && <div className="flow-node-err">{d.error}</div>}
        {d.status === 'running' ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 5 }}>
            <span className="loading-spinner" style={{ width: 13, height: 13 }} />
            <span style={{ fontSize: 11, color: 'var(--text2)' }}>{d.summary || '运行中…'}</span>
          </div>
        ) : d.summary && <div className="flow-node-sum">{d.summary}</div>}
        {d.editable && <InlineText d={d} nodeId={id} />}
        {d.previews?.length > 0 && (
          <div className="flow-node-thumbs nodrag">
            {d.previews.map((p, i) => p.type === 'img'
              ? <img key={i} src={p.src} alt="" onClick={() => d.onZoom?.(p)} />
              : <video key={i} src={p.src} muted preload="metadata" onClick={() => d.onZoom?.(p)} />)}
          </div>
        )}
        {d.chips?.length > 0 && (
          <div className="flow-node-chips">
            {d.chips.map(c => (
              <ChipSelect key={c.key} chip={c} flowId={d.flowId} nodeId={id}
                nodeParams={d.nodeParams || {}} onSaved={d.onChanged} />
            ))}
          </div>
        )}
      </div>
      {d.nodeType !== 'prompt' && <Handle type="target" position={Position.Left} />}
      {d.nodeType !== 'merge' && <Handle type="source" position={Position.Right} />}
    </div>
  )
}
