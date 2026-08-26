import { useState, useEffect, useRef } from 'react'
import { api } from '../api/client'
import { useToast } from '../store/useToast'
import { useModels } from '../store/useModels'

const stepMap: Record<string, string> = {
  init: '⏳ 初始化', segment: '📝 文稿分段', tts: '🔊 TTS 配音',
  visual: '🎬 画面生成', compose: '🎞 视频合成', merge: '🔗 最终拼接', completed: '✅ 完成',
}
const stepOrder = ['init', 'segment', 'tts', 'visual', 'compose', 'merge', 'completed']

export function AnchorPage() {
  const toast = useToast()
  const models = useModels()
  const [script, setScript] = useState('')
  const [mode, setMode] = useState('A')
  const [voice, setVoice] = useState('zh-CN-XiaoxiaoNeural')
  const [minDuration, setMinDuration] = useState(5)
  const [videoPrompt, setVideoPrompt] = useState('')
  const [avatarFile, setAvatarFile] = useState('')
  const [textModel, setTextModel] = useState('agnes-2.5-flash')
  const [videoModel, setVideoModel] = useState('agnes-video-v2.0')
  const [loading, setLoading] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [task, setTask] = useState<any>(null)
  const timerRef = useRef<number>(0)

  useEffect(() => {
    if (models?.defaults?.text_model) setTextModel(models.defaults.text_model)
    if (models?.defaults?.video_model) setVideoModel(models.defaults.video_model)
  }, [models])

  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [])

  const startPolling = (id: string) => {
    timerRef.current = window.setInterval(async () => {
      try {
        const data = await api.anchorStatus(id)
        setTask(data.task)
        if (['completed', 'failed', 'cancelled'].includes(data.task?.status)) {
          clearInterval(timerRef.current)
        }
      } catch { /* ignore */ }
    }, 3000)
  }

  const handleFile = async (file: File) => {
    try {
      const data = await api.anchorUpload(file)
      if (data.success) setAvatarFile(data.filename)
      else toast.show(data.error || '上传失败', 'error')
    } catch { toast.show('上传失败', 'error') }
  }

  const generate = async () => {
    if (!script) { toast.show('请输入文稿内容', 'error'); return }
    if (mode === 'C' && !videoPrompt) { toast.show('请输入画面风格提示词', 'error'); return }
    setLoading(true)
    try {
      const data = await api.anchorGenerate({
        script, mode, voice, avatar_file: avatarFile, video_prompt: videoPrompt,
        min_duration: minDuration, text_model: textModel, video_model: videoModel,
      })
      if (data.success) {
        setTaskId(data.task_id)
        startPolling(data.task_id)
        toast.show('任务已提交！', 'success')
      }
    } catch (e: any) {
      toast.show(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const currentIdx = task ? stepOrder.indexOf(task.step) : -1

  return (
    <div className="card">
      <div className="card-header"><span style={{ fontSize: 20 }}>🎙</span> 数字人口播视频</div>
      <p style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 12 }}>
        输入文稿内容，选择模式后自动生成带 TTS 配音和字幕的口播视频。
      </p>

      <div className="form-group">
        <label className="form-label">📝 文稿内容</label>
        <textarea className="form-textarea" value={script} onChange={e => setScript(e.target.value)} rows={8}
          placeholder="请输入或粘贴口播文稿内容..." />
      </div>

      <div className="form-group">
        <label className="form-label">🎬 画面模式</label>
        <div style={{ display: 'flex', gap: 8 }}>
          {['A', 'B', 'C'].map(m => (
            <label key={m} style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px',
              background: 'var(--surface2)', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
              border: `2px solid ${mode === m ? 'var(--accent)' : 'transparent'}`, fontSize: 13,
            }}>
              <input type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} />
              {m === 'A' ? 'A. 静态形象图' : m === 'B' ? 'B. 视频素材' : 'C. AI 生成画面'}
            </label>
          ))}
        </div>
      </div>

      {mode === 'A' && (
        <div className="form-group">
          <label className="form-label">🖼 上传数字人形象图片</label>
          <input type="file" accept="image/*" onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} style={{ fontSize: 13 }} />
        </div>
      )}
      {mode === 'B' && (
        <div className="form-group">
          <label className="form-label">🎥 上传数字人视频素材</label>
          <input type="file" accept="video/*" onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} style={{ fontSize: 13 }} />
        </div>
      )}
      {mode === 'C' && (
        <div className="form-group">
          <label className="form-label">✨ 画面风格提示词</label>
          <textarea className="form-textarea" value={videoPrompt} onChange={e => setVideoPrompt(e.target.value)} rows={3}
            placeholder="描述画面风格..." />
        </div>
      )}

      <div className="form-row">
        <div className="form-group">
          <label className="form-label">🔊 TTS 音色</label>
          <select className="form-select" value={voice} onChange={e => setVoice(e.target.value)}>
            <option value="zh-CN-XiaoxiaoNeural">晓晓（女声·温暖）</option>
            <option value="zh-CN-YunxiNeural">云希（男声·阳光）</option>
            <option value="zh-CN-YunjianNeural">云健（男声·沉稳）</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">⏱ 每段最小时长</label>
          <select className="form-select" value={minDuration} onChange={e => setMinDuration(Number(e.target.value))}>
            {[3, 5, 8, 10, 15, 20].map(v => <option key={v} value={v}>{v} 秒</option>)}
          </select>
        </div>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label className="form-label">📝 文本模型</label>
          <select className="form-select" value={textModel} onChange={e => setTextModel(e.target.value)}>
            {models && Object.entries(models.text_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">🎬 视频模型 (C 模式)</label>
          <select className="form-select" value={videoModel} onChange={e => setVideoModel(e.target.value)}>
            {models && Object.entries(models.video_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
        </div>
      </div>

      <button className="btn btn-primary" onClick={generate} disabled={loading} style={{ width: '100%', padding: 10 }}>
        {loading ? <><span className="loading-spinner" /> 处理中...</> : '🎙 开始生成数字人口播视频'}
      </button>

      {task && (
        <div style={{ marginTop: 16 }}>
          <div className="card" style={{ background: 'var(--surface2)' }}>
            <div className="card-header">📊 生成进度</div>
            <div style={{ marginBottom: 12 }}>
              {stepOrder.map((s, i) => {
                const done = i < currentIdx; const current = i === currentIdx
                return (
                  <span key={s} style={{
                    color: done ? 'var(--success)' : current ? 'var(--accent)' : 'var(--text2)',
                    fontWeight: current ? 600 : 400, marginRight: 12, fontSize: 12,
                  }}>{stepMap[s] || s}</span>
                )
              })}
            </div>
            <div style={{ color: 'var(--text2)', fontSize: 12 }}>{task.message || ''}</div>
            {task.segments && (
              <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {task.segments.map((seg: any, i: number) => (
                  <div key={i} style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 4, padding: '6px 10px', fontSize: 11 }}>
                    第{i + 1}段 {seg.duration ? `${seg.duration}s` : '--'} | 🎵{seg.audio_file ? '✅' : '⏳'} 🎬{seg.visual_path ? '✅' : '⏳'}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {task?.status === 'completed' && task?.output_file && (
        <div style={{ marginTop: 16 }}>
          <div className="card" style={{ background: 'var(--surface2)' }}>
            <div className="card-header">🎥 生成结果</div>
            <video controls style={{ width: '100%', maxWidth: 600, borderRadius: 'var(--radius-sm)' }}
              src={`/anchor/${taskId}/${task.output_file}`} />
          </div>
        </div>
      )}
    </div>
  )
}