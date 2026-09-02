import { useEffect, useState } from 'react'
import { api } from '../api/client'

export function FilesPage() {
  const [tab, setTab] = useState('pictures')
  const [files, setFiles] = useState<any[]>([])

  const load = async () => {
    try {
      const data = await api.listFiles(tab, 'all')
      setFiles(data.files || [])
    } catch { /* ignore */ }
  }

  useEffect(() => { load() }, [tab])

  return (
    <div className="card">
      <div className="card-header">
        <span style={{ fontSize: 20 }}>📁</span> 本地生成文件
        <button className="btn btn-sm" style={{ marginLeft: 'auto' }} onClick={load}>🔄 刷新</button>
      </div>
      <div style={{ marginBottom: 12, display: 'flex', gap: 8 }}>
        <button className="btn btn-sm" style={{ background: tab === 'pictures' ? 'var(--accent)' : 'var(--surface2)', borderColor: tab === 'pictures' ? 'var(--accent)' : 'var(--border)' }} onClick={() => setTab('pictures')}>🖼 图片</button>
        <button className="btn btn-sm" style={{ background: tab === 'videos' ? 'var(--accent)' : 'var(--surface2)', borderColor: tab === 'videos' ? 'var(--accent)' : 'var(--border)' }} onClick={() => setTab('videos')}>🎬 视频</button>
      </div>
      <div className="task-list">
        {files.length === 0 ? (
          <p style={{ color: 'var(--text2)', textAlign: 'center', padding: 20 }}>暂无文件</p>
        ) : files.map(f => (
          <div key={f.url} className="task-item" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 10 }}>
            <div style={{ display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="task-info">
                <div className="task-prompt" style={{ fontFamily: 'monospace', fontSize: 12 }}>{f.filename}</div>
                <div className="task-time">{f.modified} | {f.size_display}</div>
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                <button className="btn btn-sm btn-success" onClick={() => window.open(f.url)}>👁 查看</button>
                <button className="btn btn-sm" onClick={() => { navigator.clipboard.writeText(window.location.origin + f.url) }}>📋 复制</button>
              </div>
            </div>
            {tab === 'videos' ? (
              <video src={f.url} style={{ width: '100%', maxWidth: 300, borderRadius: 'var(--radius-sm)' }} controls />
            ) : (
              <img src={f.url} style={{ width: '100%', maxWidth: 300, borderRadius: 'var(--radius-sm)' }} loading="lazy" />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}