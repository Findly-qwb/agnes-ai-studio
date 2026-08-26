import { useEffect, useState } from 'react'
import { api } from '../api/client'

export function VideoTasksPage() {
  const [tasks, setTasks] = useState<any[]>([])

  const load = async () => {
    try {
      const data = await api.listVideoTasks()
      setTasks(data.tasks || [])
    } catch { /* ignore */ }
  }

  useEffect(() => { load() }, [])

  const statusLabels: Record<string, string> = { queued: '排队中', in_progress: '生成中', completed: '已完成', failed: '失败' }

  return (
    <div className="card">
      <div className="card-header">
        <span style={{ fontSize: 20 }}>📋</span> 视频任务列表
        <button className="btn btn-sm" style={{ marginLeft: 'auto' }} onClick={load}>🔄 刷新</button>
      </div>
      <div className="task-list">
        {tasks.length === 0 ? (
          <p style={{ color: 'var(--text2)', textAlign: 'center', padding: 20 }}>暂无视频任务</p>
        ) : tasks.map(t => (
          <div key={t.task_id} className="task-item">
            <div className="task-info">
              <div className="task-prompt">{t.prompt}</div>
              <div className="task-time">{new Date(t.created_at * 1000).toLocaleString('zh-CN')}</div>
            </div>
            <span className={`task-status status-${t.status}`}>{statusLabels[t.status] || t.status}</span>
            <div style={{ display: 'flex', gap: 4 }}>
              {t.status === 'completed' && t.video_url && (
                <>
                  <button className="btn btn-sm btn-success" onClick={() => window.open(t.video_url)}>▶ 播放</button>
                  <button className="btn btn-sm" onClick={() => navigator.clipboard.writeText(t.video_url)}>📋 复制</button>
                </>
              )}
              {(t.status === 'queued' || t.status === 'in_progress') && (
                <button className="btn btn-sm" onClick={load}>🔄 刷新</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}