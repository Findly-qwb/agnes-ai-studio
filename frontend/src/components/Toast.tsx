import { useToast } from '../store/useToast'

const colorMap = {
  success: { bg: '#dcfce7', color: '#15803d', border: '#86efac' },
  error: { bg: '#fee2e2', color: '#b91c1c', border: '#fca5a5' },
  info: { bg: '#dbeafe', color: '#1d4ed8', border: '#93c5fd' },
}

export function Toast() {
  const { message, type, visible } = useToast()
  const c = colorMap[type]
  return (
    <div style={{
      position: 'fixed', top: 20, right: 20, zIndex: 300,
      padding: '12px 20px', borderRadius: 8,
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
      fontWeight: 500, fontSize: 14, display: visible ? 'block' : 'none',
      animation: 'slideIn 0.3s ease',
    }}>
      {message}
    </div>
  )
}