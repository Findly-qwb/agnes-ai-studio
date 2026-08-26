import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'

interface LayoutProps {
  activeTab: string
  onTabChange: (tab: string) => void
  children: ReactNode
  onOpenSettings: () => void
}

const tabs = [
  { key: 'image', label: '🖼 文生图' },
  { key: 'img2img', label: '🎨 图生图' },
  { key: 'video', label: '🎬 视频生成' },
  { key: 'videoTasks', label: '📋 视频任务' },
  { key: 'drama', label: '🎭 短剧生成' },
  { key: 'anchor', label: '🎙 数字人口播' },
  { key: 'files', label: '📁 本地文件' },
]

export function Layout({ activeTab, onTabChange, children, onOpenSettings }: LayoutProps) {
  const [keyStatus, setKeyStatus] = useState('')

  useEffect(() => {
    api.getConfig().then(d => {
      setKeyStatus(d.api_key_masked ? d.api_key_masked : '')
    }).catch(() => {})
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <header style={{
        background: 'var(--surface)', borderBottom: '1px solid var(--border)',
        padding: '0 20px', height: 'var(--header-h)', display: 'flex',
        alignItems: 'center', justifyContent: 'space-between', position: 'sticky', top: 0, zIndex: 100,
      }}>
        <div style={{ fontSize: 20, fontWeight: 700, background: 'linear-gradient(135deg, var(--accent), #a855f7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          ✦ Agnes AI Studio
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 12, color: 'var(--text2)' }}>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: keyStatus ? 'var(--success)' : 'var(--error)', marginRight: 4 }} />
            {keyStatus ? `API Key: ${keyStatus}` : '未配置 API Key'}
          </span>
          <button className="btn btn-sm" onClick={onOpenSettings}>⚙ 设置</button>
        </div>
      </header>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <nav style={{
          width: 'var(--sidebar-w)', background: 'var(--surface)',
          borderRight: '1px solid var(--border)', padding: '12px 0', flexShrink: 0, overflowY: 'auto',
        }}>
          {tabs.map(t => (
            <button key={t.key} onClick={() => onTabChange(t.key)} style={{
              display: 'block', width: '100%', padding: '10px 20px', textAlign: 'left',
              background: activeTab === t.key ? 'var(--surface2)' : 'transparent',
              color: activeTab === t.key ? 'var(--accent)' : 'var(--text2)',
              border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: activeTab === t.key ? 600 : 400,
              transition: 'all 0.15s', borderLeft: activeTab === t.key ? '3px solid var(--accent)' : '3px solid transparent',
            }}>
              {t.label}
            </button>
          ))}
        </nav>

        <main style={{ flex: 1, padding: 20, overflowY: 'auto', background: 'var(--bg)' }}>
          {children}
        </main>
      </div>
    </div>
  )
}