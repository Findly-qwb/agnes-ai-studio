import { useState, useRef, useEffect } from 'react'
import { api } from '../api/client'
import { useToast } from '../store/useToast'
import { PromptInput, VIDEO_RATIOS, secondsToFrames, type PromptConfig } from '../components/PromptInput'

export function HomePage() {
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [videoProgress, setVideoProgress] = useState(0)
  const [history, setHistory] = useState<any[]>([])
  const timerRef = useRef<number>(0)

  useEffect(() => {
    const load = async () => {
      try {
        const [p, v] = await Promise.all([api.listFiles('pictures'), api.listFiles('videos')])
        setHistory([
          ...(p.files || []).map((f: any) => ({ ...f, type: 'image' })),
          ...(v.files || []).map((f: any) => ({ ...f, type: 'video' })),
        ].sort((a, b) => (a.modified < b.modified ? 1 : -1)).slice(0, 60))
      } catch { /* ignore */ }
    }
    load()
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [result])

  const startPolling = (id: string) => {
    let n = 0
    timerRef.current = window.setInterval(async () => {
      n++
      try {
        const data = await api.videoStatus(id)
        setVideoProgress(Math.min(n * 2, 95))
        if (data.status === 'completed') {
          clearInterval(timerRef.current)
          setVideoProgress(100)
          setLoading(false)
          setResult({ kind: 'video', url: data.video_url || (data.local_file ? `/videos/${data.local_file}` : ''), data })
          toast.show('视频生成完成！', 'success')
        } else if (data.status === 'failed') {
          clearInterval(timerRef.current)
          setLoading(false)
          setVideoProgress(0)
          toast.show('视频生成失败', 'error')
        }
      } catch { /* ignore */ }
    }, 10000)
  }

  const generate = async (cfg: PromptConfig) => {
    setLoading(true)
    setResult(null)
    try {
      if (cfg.mode === 'video') {
        setVideoProgress(5)
        const [width, height] = VIDEO_RATIOS[cfg.videoRatio]
        const data = await api.generateVideo({
          prompt: cfg.prompt, model: cfg.model,
          width, height, num_frames: secondsToFrames(cfg.videoSeconds, cfg.fps), frame_rate: cfg.fps,
          image_url: cfg.imageUrl,
        })
        startPolling(data.task_id)
        toast.show('视频任务已提交，请稍候', 'info')
        return
      }
      const data = cfg.mode === 'image'
        ? await api.generateImage({ prompt: cfg.prompt, size: cfg.size, ratio: cfg.ratio, model: cfg.model, translate_prompt: cfg.translatePrompt })
        : await api.img2img({ prompt: cfg.prompt, image_url: cfg.imageUrl!, size: cfg.size, ratio: cfg.ratio, model: cfg.model, translate_prompt: cfg.translatePrompt })
      setResult({ kind: 'image', url: data.image_url, data })
      toast.show('生成成功！', 'success')
    } catch (e: any) {
      toast.show(e.message, 'error')
      if (cfg.mode === 'video') setVideoProgress(0)
    } finally {
      setLoading(false)
    }
  }

  const busy = loading || (videoProgress > 0 && videoProgress < 100)

  return (
    <div>
      <div className="hero-title">灵感，即刻成片</div>
      <div className="hero-sub">选择模式，输入描述，直接在首页生成图片与视频</div>

      <PromptInput busy={busy} onSubmit={generate} />

      {videoProgress > 0 && videoProgress < 100 && (
        <div className="home-result">
          <div className="card" style={{ background: 'var(--surface2)' }}>
            <div className="card-header">🎥 视频生成中... {videoProgress}%</div>
            <div style={{ background: 'var(--border)', borderRadius: 4, height: 4, overflow: 'hidden' }}>
              <div style={{ width: `${videoProgress}%`, height: '100%', background: 'var(--accent)', transition: 'width 0.5s' }} />
            </div>
          </div>
        </div>
      )}

      {result && (
        <div className="home-result">
          <div className="card">
            <div className="card-header">{result.kind === 'video' ? '🎬 生成结果' : '🖼 生成结果'}</div>
            {result.kind === 'video'
              ? <video className="result-video" src={result.url} controls autoPlay />
              : <img className="result-image" src={result.url} alt="" />}
            <div className="result-actions">
              <button className="btn btn-sm" onClick={() => window.open(result.url)}>📥 打开</button>
              <button className="btn btn-sm" onClick={() => { navigator.clipboard.writeText(result.url); toast.show('已复制', 'success') }}>📋 复制URL</button>
              <button className="btn btn-sm" onClick={() => { setResult(null); setVideoProgress(0) }}>✕ 关闭</button>
            </div>
          </div>
        </div>
      )}

      <div className="home-section-title">✦ 生成历史</div>
      {history.length === 0 ? (
        <p style={{ color: 'var(--text2)', textAlign: 'center', padding: 30 }}>还没有作品，从上方开始第一次创作</p>
      ) : (
        <div className="masonry">
          {history.map(f => (
            <div key={f.url} className="masonry-item" onClick={() => window.open(f.url)} title={`${f.filename} · ${f.modified}`}>
              <span className="media-type">{f.type === 'video' ? '🎬' : '🖼'}</span>
              {f.type === 'video'
                ? <video src={`${f.url}#t=0.1`} muted preload="metadata" />
                : <img src={f.url} alt="" loading="lazy" />}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
