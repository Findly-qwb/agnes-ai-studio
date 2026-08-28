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
  { key: 'home', label: '首页', icon: '✦' },
  { key: 'image', label: '文生图', icon: '🖼' },
  { key: 'img2img', label: '图生图', icon: '🎨' },
  { key: 'video', label: '视频', icon: '🎬' },
  { key: 'videoTasks', label: '任务', icon: '📋' },
  { key: 'drama', label: '短剧', icon: '🎭' },
  { key: 'dramaFlow', label: '节点流', icon: '🕸' },
  { key: 'anchor', label: '数字人', icon: '🎙' },
  { key: 'files', label: '文件', icon: '📁' },
]

export function Layout({ activeTab, onTabChange, children, onOpenSettings }: LayoutProps) {
  const [keyStatus, setKeyStatus] = useState('')

  useEffect(() => {
    api.getConfig().then(d => {
      setKeyStatus(d.api_key_masked ? d.api_key_masked : '')
    }).catch(() => { })
  }, [])

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <nav className="float-nav">
        <div style={{
          textAlign: 'center', fontSize: 22, marginBottom: 14,
          background: 'linear-gradient(135deg, var(--accent), #a855f7)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', fontWeight: 700,
        }}>✦</div>
        {tabs.map(t => (
          <button key={t.key} onClick={() => onTabChange(t.key)} title={t.label} className="float-nav-btn" style={{
            background: activeTab === t.key ? 'rgba(99,102,241,0.18)' : 'transparent',
            color: activeTab === t.key ? 'var(--accent)' : 'var(--text2)',
          }}>
            <span style={{ fontSize: 18 }}>{t.icon}</span>
            <span style={{ fontSize: 11, fontWeight: activeTab === t.key ? 600 : 400 }}>{t.label}</span>
          </button>
        ))}
        <button onClick={onOpenSettings} title="设置" className="float-nav-btn" style={{ marginTop: 'auto' }}>
          <span style={{ fontSize: 18 }}>⚙</span>
          <span style={{ fontSize: 11 }}>设置</span>
        </button>
      </nav>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <header style={{
          background: 'color-mix(in srgb, var(--surface) 80%, transparent)',
          backdropFilter: 'blur(12px)', borderBottom: '1px solid var(--border)',
          padding: '0 10px', height: 'var(--header-h)', display: 'flex',
          alignItems: 'center', justifyContent: 'flex-end', flexShrink: 0,
        }}>
          <span style={{ fontSize: 12, color: 'var(--text2)', cursor: 'default' }}
            title={keyStatus ? `API Key: ${keyStatus}` : undefined}>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: keyStatus ? 'var(--success)' : 'var(--error)', marginRight: 4 }} />
            {keyStatus ? '已配置' : '未配置 API Key'}
          </span>
        </header>
        <main style={{ flex: 1, padding: activeTab === 'dramaFlow' ? 16 : 90, overflowY: 'auto', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
          {children}
        </main>
      </div>
    </div>
  )
}
