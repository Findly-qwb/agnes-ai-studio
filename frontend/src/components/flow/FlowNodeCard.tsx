// 画布自定义节点卡片（n8n 外观 + ComfyUI 式内联参数 widget）
import { type CSSProperties, useState } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { api } from '../../api/client'

export type Chip = {
  key: string
  label: string
  value: string
  options: [string, string][]
}

export type FlowNodeData = {
  nodeType: string
  label: string
  status: string
  error: string
  summary: string
  thumbs: string[]
  chips: Chip[]
  flowId: string
  nodeParams: Record<string, unknown>
  onChipSaved?: () => void
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
          if (v === chip.value) delete merged[chip.key]
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

export function FlowNodeCard({ data, selected, id }: NodeProps) {
  const d = data as unknown as FlowNodeData
  return (
    <div className={`flow-node${selected ? ' selected' : ''}`}
      style={{ '--type-color': TYPE_COLORS[d.nodeType] || 'var(--accent)' } as CSSProperties}>
      <span className="flow-node-bar" />
      <div className="flow-node-body">
        <div className="flow-node-head">
          <b>{d.label}</b>
          <span className={`flow-dot ${d.status}`} title={STATUS_LABELS[d.status] || d.status} />
        </div>
        {d.error && <div className="flow-node-err">{d.error}</div>}
        {d.summary && <div className="flow-node-sum">{d.summary}</div>}
        {d.chips?.length > 0 && (
          <div className="flow-node-chips">
            {d.chips.map(c => (
              <ChipSelect key={c.key} chip={c} flowId={d.flowId} nodeId={id}
                nodeParams={d.nodeParams || {}} onSaved={d.onChipSaved} />
            ))}
          </div>
        )}
      </div>
      {d.nodeType !== 'prompt' && <Handle type="target" position={Position.Left} />}
      {d.nodeType !== 'merge' && <Handle type="source" position={Position.Right} />}
    </div>
  )
}
