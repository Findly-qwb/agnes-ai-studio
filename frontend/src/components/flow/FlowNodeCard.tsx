// 画布自定义节点卡片
import { Handle, Position, type NodeProps } from '@xyflow/react'

export type FlowNodeData = {
  nodeType: string
  label: string
  status: string
  error: string
  summary: string
  thumbs: string[]
  [key: string]: unknown
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'var(--text2)', running: '#3b82f6', completed: 'var(--success)',
  failed: 'var(--error)', stale: '#f59e0b', stopped: 'var(--text2)',
  interrupted: '#f59e0b',
}
const STATUS_LABELS: Record<string, string> = {
  pending: '待运行', running: '运行中…', completed: '完成', failed: '失败',
  stale: '需重跑', stopped: '已停止', interrupted: '已中断',
}

export function FlowNodeCard({ data, selected }: NodeProps) {
  const d = data as unknown as FlowNodeData
  const border = d.status === 'failed' ? 'var(--error)'
    : d.status === 'completed' ? 'var(--success)'
    : d.status === 'running' ? '#3b82f6'
    : d.status === 'stale' ? '#f59e0b' : 'var(--border)'
  return (
    <div style={{
      width: 230, background: 'var(--surface)', border: `2px solid ${selected ? 'var(--accent)' : border}`,
      borderRadius: 10, padding: 10, boxShadow: '0 2px 10px rgba(0,0,0,.25)',
      fontSize: 12, color: 'var(--text)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>{d.label}</span>
        <span style={{
          fontSize: 10, padding: '1px 7px', borderRadius: 8,
          background: `color-mix(in srgb, ${STATUS_COLORS[d.status] || 'var(--text2)'} 18%, transparent)`,
          color: STATUS_COLORS[d.status] || 'var(--text2)', fontWeight: 600,
        }}>{STATUS_LABELS[d.status] || d.status}</span>
      </div>
      {d.error && <div style={{ color: 'var(--error)', fontSize: 10, maxHeight: 40, overflow: 'hidden', marginBottom: 4, wordBreak: 'break-all' }}>{d.error}</div>}
      {d.summary && <div style={{ color: 'var(--text2)', fontSize: 11, maxHeight: 44, overflow: 'hidden', whiteSpace: 'pre-wrap' }}>{d.summary}</div>}
      {d.thumbs.length > 0 && (
        <div style={{ display: 'flex', gap: 3, marginTop: 6, flexWrap: 'wrap' }}>
          {d.thumbs.slice(0, 5).map((t, i) => (
            <img key={i} src={t} style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 4, border: '1px solid var(--border)' }} />
          ))}
        </div>
      )}
      {d.nodeType !== 'prompt' && <Handle type="target" position={Position.Left} style={{ width: 9, height: 9, background: 'var(--accent)', borderColor: 'var(--accent)' }} />}
      {d.nodeType !== 'merge' && <Handle type="source" position={Position.Right} style={{ width: 9, height: 9, background: 'var(--accent)', borderColor: 'var(--accent)' }} />}
    </div>
  )
}
