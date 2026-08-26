import type { ReactNode } from 'react'

interface ModalProps {
  show: boolean
  title?: string
  children: ReactNode
  onClose?: () => void
  actions?: ReactNode
  maxWidth?: number
}

export function Modal({ show, title, children, actions, maxWidth = 480, onClose }: ModalProps) {
  if (!show) return null
  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', }}
      onClick={onClose}
    >
      <div
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 24, width: '90%', maxWidth, maxHeight: "600px", overflowY: "auto" }}
        onClick={e => e.stopPropagation()}

      >
        {title && <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>{title}</div>}
        {children}
        {actions && <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 20 }}>{actions}</div>}
      </div>
    </div>
  )
}