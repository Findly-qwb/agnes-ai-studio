import { useState, useRef } from 'react'

interface DropZoneProps {
  onFile: (file: File) => void
  imageUrl?: string
  onRemove?: () => void
  accept?: string
}

export function DropZone({ onFile, imageUrl, onRemove, accept = 'image/*' }: DropZoneProps) {
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) onFile(file)
  }

  if (imageUrl) {
    return (
      <div style={{ position: 'relative', border: `2px solid var(--success)`, borderRadius: 'var(--radius)', overflow: 'hidden' }}>
        <img src={imageUrl} style={{ width: '100%', maxHeight: 240, objectFit: 'contain', display: 'block' }} />
        {onRemove && (
          <button onClick={onRemove} style={{
            position: 'absolute', top: 8, right: 8, width: 24, height: 24, borderRadius: '50%',
            background: 'rgba(0,0,0,0.7)', color: '#fff', border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
          }}>✕</button>
        )}
      </div>
    )
  }

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      style={{
        border: `2px dashed ${dragOver ? 'var(--accent)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)', padding: '30px 20px', textAlign: 'center',
        cursor: 'pointer', background: dragOver ? 'rgba(99,102,241,0.08)' : 'var(--surface2)',
        transition: 'all 0.2s',
      }}
    >
      <div style={{ fontSize: 36, marginBottom: 8, opacity: 0.6 }}>🖼</div>
      <div style={{ fontSize: 13, color: 'var(--text2)' }}>
        拖拽图片到此处，或<strong style={{ color: 'var(--accent)' }}>点击选择</strong>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 6, opacity: 0.7 }}>支持 JPG / PNG / GIF / WebP</div>
      <input ref={inputRef} type="file" accept={accept} style={{ display: 'none' }} onChange={e => {
        if (e.target.files?.[0]) onFile(e.target.files[0])
        e.target.value = ''
      }} />
    </div>
  )
}