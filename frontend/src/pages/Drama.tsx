import { useEffect, useState, useRef } from 'react'
import { api } from '../api/client'
import { useToast } from '../store/useToast'
import { useDramaStore } from '../store/useDramaStore'
import { useModels } from '../store/useModels'

const stepLabels: Record<string, string> = {
  pending: '等待中', step1: '① 生成故事+剧本...', paused_story: '⏸ 请确认故事梗概',
  step2: '② 生成分镜...', step3: '③ 提取素材...', paused: '⏸ 请确认参考图',
  paused_video: '⏸ 请逐个启动视频生成', step4: '④ 生成视频...',
  completed: '✅ 完成', failed: '❌ 失败', stopped: '⏹ 已停止',
}
const stepProgress: Record<string, number> = {
  step1: 15, paused_story: 18, step2: 35, step3: 55, paused: 60, paused_video: 65, step4: 75, completed: 100, failed: 100, stopped: 100,
}

export function DramaPage() {
  const toast = useToast()
  const store = useDramaStore()
  const models = useModels()
  const [prompt, setPrompt] = useState('')
  const [shotDuration, setShotDuration] = useState(5)
  const [textModel, setTextModel] = useState('agnes-2.5-flash')
  const [imageModel, setImageModel] = useState('agnes-image-2.1-flash')
  const [videoModel, setVideoModel] = useState('agnes-video-v2.0')
  const [charStyle, setCharStyle] = useState('anime')
  const [starting, setStarting] = useState(false)
  const [storyEdit, setStoryEdit] = useState('')
  const [mergeName, setMergeName] = useState('')
  const shotPromptValues = useRef<Record<number, string>>({})
  const assetPromptValues = useRef<Record<number, string>>({})

  useEffect(() => {
    if (models?.defaults) {
      setTextModel(models.defaults.text_model)
      setImageModel(models.defaults.image_model)
      setVideoModel(models.defaults.video_model)
    }
  }, [models])

  useEffect(() => {
    const saved = localStorage.getItem('currentDramaId')
    if (saved) {
      api.dramaStatus(saved).then(res => {
        if (res.success) {
          store.restore(saved)
        }
      }).catch(() => localStorage.removeItem('currentDramaId'))
    }
  }, [])

  useEffect(() => {
    if (!store.polling) return
    const timer = setInterval(() => store.pollStatus(), 8000)
    store.pollStatus()
    return () => clearInterval(timer)
  }, [store.polling])

  const handleStart = async () => {
    if (!prompt) { toast.show('请输入短剧描述', 'error'); return }
    setStarting(true)
    store.clear()
    store.setStoryConfirmed(false)
    await store.startDrama({ prompt, shot_duration: shotDuration, text_model: textModel, image_model: imageModel, video_model: videoModel, character_style: charStyle })
    setStarting(false)
  }

  const handleStop = async () => {
    await store.stopDrama()
    toast.show('已发送停止信号', 'info')
  }

  const handleStoryConfirm = async (edited?: string) => {
    if (!store.currentId) return
    try {
      await api.storyConfirm(store.currentId, edited)
      store.setStoryConfirmed(true)
    } catch (e: any) { toast.show('确认失败: ' + e.message, 'error') }
  }

  const handleResume = async () => {
    if (!store.currentId) return
    try {
      await api.dramaResume(store.currentId)
      toast.show('已确认参考图', 'success')
    } catch (e: any) { toast.show('恢复失败: ' + e.message, 'error') }
  }

  // ---- 素材操作 ----
  const handleAssetReplace = async (idx: number, file: File) => {
    if (!store.currentId) return
    try {
      await api.assetReplace(store.currentId, idx, file)
      toast.show('参考图替换成功', 'success')
      store.pollStatus()
    } catch (e: any) { toast.show('替换失败: ' + e.message, 'error') }
  }

  const handleAssetRegen = async (idx: number) => {
    if (!store.currentId) return
    try {
      const customDesc = assetPromptValues.current[idx]
      await api.assetRegenerate({ drama_id: store.currentId, asset_index: idx, ...(customDesc ? { custom_desc: customDesc } : {}) })
      toast.show('参考图重新生成中', 'success')
      store.pollStatus()
    } catch (e: any) { toast.show('重新生成失败: ' + e.message, 'error') }
  }

  // ---- 镜头操作 ----
  const handleShotStart = async (si: number) => {
    if (!store.currentId) return
    try {
      await api.shotRegenerate({ drama_id: store.currentId, shot_index: si })
      toast.show(`镜头 ${si} 开始生成`, 'success')
      store.pollStatus()
    } catch (e: any) { toast.show('启动失败: ' + e.message, 'error') }
  }

  const handleShotRegen = async (si: number) => {
    if (!store.currentId) return
    try {
      const custom = shotPromptValues.current[si]
      await api.shotRegenerate({ drama_id: store.currentId, shot_index: si, ...(custom ? { custom_prompt: custom } : {}) })
      toast.show(`镜头 ${si} 开始重新生成`, 'success')
      store.pollStatus()
    } catch (e: any) { toast.show('重新生成失败: ' + e.message, 'error') }
  }

  const handleUploadRefImage = async (si: number, file: File) => {
    if (!store.currentId) return
    try {
      await api.shotUploadImage(store.currentId, si, file)
      toast.show(`镜头 ${si} 参考图已上传`, 'success')
      store.pollStatus()
    } catch (e: any) { toast.show('上传失败: ' + e.message, 'error') }
  }

  const handleDeleteRefImage = async (si: number, imgIdx: number) => {
    if (!store.currentId) return
    if (!confirm(`确定删除镜头 ${si} 的第 ${imgIdx + 1} 张参考图吗？`)) return
    try {
      await api.shotDeleteImage({ drama_id: store.currentId, shot_index: si, image_index: imgIdx })
      toast.show('已删除', 'success')
      store.pollStatus()
    } catch (e: any) { toast.show('删除失败: ' + e.message, 'error') }
  }

  // ---- 合并操作 ----
  const moveMergeShot = (idx: number, dir: number) => {
    const arr = [...store.mergeSelected]
    const ni = idx + dir
    if (ni < 0 || ni >= arr.length) return
    ;[arr[idx], arr[ni]] = [arr[ni], arr[idx]]
    store.setMergeSelected(arr)
  }
  const removeMergeShot = (idx: number) => {
    store.setMergeSelected(store.mergeSelected.filter((_, i) => i !== idx))
  }
  const doMerge = async () => {
    if (store.mergeSelected.length < 2) { toast.show('请至少选择 2 个镜头', 'error'); return }
    const name = mergeName.trim() || `merge_${Date.now() % 10000}`
    try {
      await api.mergeCustom({ drama_id: store.currentId, shot_indices: store.mergeSelected, merge_name: name })
      toast.show('合并成功！', 'success')
      setMergeName('')
      store.pollStatus()
    } catch (e: any) { toast.show('合并失败: ' + e.message, 'error') }
  }

  const d = store.data
  const progress = d ? stepProgress[d.status] || 5 : 0
  const barColor = d?.status === 'failed' ? 'var(--error)' : d?.status === 'completed' ? 'var(--success)' : d?.status === 'stopped' ? 'var(--text2)' : 'var(--accent)'

  // ---- 素材卡片 ----
  const renderAsset = (a: any, idx: number) => {
    const catLabel: Record<string, string> = { characters: '角色', scenes: '场景', props: '道具' }
    const imgSrc = a.local_file ? `/dramas/${store.currentId}/images/${a.local_file}` : a.image_url || ''
    const hasImage = !!imgSrc
    const isGenerating = d?.status === 'step3'
    const isFailed = !hasImage && !isGenerating

    return (
      <div key={idx} style={{ background: 'var(--bg)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', overflow: 'hidden' }}>
        {hasImage ? (
          <img src={imgSrc} style={{ width: '100%', height: 160, objectFit: 'cover' }} />
        ) : isGenerating ? (
          <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text2)', fontSize: 12 }}>
            <span className="loading-spinner" style={{ marginRight: 6 }} />生成中...
          </div>
        ) : (
          <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--error)', fontSize: 12 }}>❌ 生成失败</div>
        )}
        <div style={{ padding: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{a.name} <span style={{ fontSize: 10, color: 'var(--accent)' }}>[{catLabel[a.category] || a.category}]</span></span>
            <div style={{ display: 'flex', gap: 4 }}>
              {isFailed && (
                <button style={{ fontSize: 11, color: '#fff', background: 'var(--error)', border: 'none', borderRadius: 4, padding: '2px 8px', cursor: 'pointer' }} onClick={() => handleAssetRegen(idx)}>重新生成</button>
              )}
              <label style={{ cursor: 'pointer', fontSize: 11, color: 'var(--accent)', padding: '2px 6px', border: '1px solid var(--accent)', borderRadius: 4 }}>
                替换
                <input type="file" accept="image/*" style={{ display: 'none' }} onChange={e => { if (e.target.files?.[0]) handleAssetReplace(idx, e.target.files[0]); e.target.value = '' }} />
              </label>
            </div>
          </div>
          <div style={{ marginTop: 6 }}>
            <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 3 }}>📝 角色描述（可编辑后重新生成）</div>
            <textarea style={{ width: '100%', minHeight: 80, fontSize: 13, fontFamily: 'monospace', background: 'var(--surface2)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 4, padding: 6, resize: 'vertical', lineHeight: 1.4 }}
              defaultValue={a.desc || a.img_prompt || ''}
              onChange={e => { assetPromptValues.current[idx] = e.target.value }} />
            <button style={{ fontSize: 12, color: '#fff', background: 'var(--accent)', border: 'none', borderRadius: 4, padding: '3px 10px', cursor: 'pointer', marginTop: 4 }} onClick={() => handleAssetRegen(idx)}>✏️ 修改并重新生成</button>
          </div>
        </div>
      </div>
    )
  }

  // ---- 镜头信息面板 ----
  const renderInfoPanel = (v: any) => {
    const si = v.shot_index
    const detail = d?.shot_details?.[si] || {}
    const videoPrompt = detail.video_prompt_cn || detail.video_prompt || v.prompt || ''
    const refImages = detail.reference_images || []

    const refImgsHtml = refImages.map((img: any, imgIdx: number) => {
      const imgSrc = img.local_file ? `/dramas/${store.currentId}/images/${img.local_file}` : img.image_url || ''
      return (
        <div key={imgIdx} style={{ position: 'relative', display: 'inline-block', width: 56, height: 56 }} title={img.asset_name || ''}>
          <img src={imgSrc} style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 4, border: '1px solid var(--border)' }} />
          <button onClick={() => handleDeleteRefImage(si, imgIdx)} style={{
            position: 'absolute', top: -4, right: -4, width: 16, height: 16, borderRadius: '50%',
            background: 'var(--error)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 10,
            lineHeight: 1, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }} title="删除此参考图">✕</button>
        </div>
      )
    })

    const uploadBtn = (
      <label style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 56, height: 56, border: '1px dashed var(--border)', borderRadius: 4, cursor: 'pointer', color: 'var(--text2)', fontSize: 16 }} title="上传参考图">
        +<input type="file" accept="image/*" style={{ display: 'none' }} onChange={e => { if (e.target.files?.[0]) handleUploadRefImage(si, e.target.files[0]); e.target.value = '' }} />
      </label>
    )

    return (
      <div style={{ flex: 1, minWidth: 200, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 600, marginBottom: 3 }}>参考图 ({refImages.length})</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'center' }}>
            {refImgsHtml}
            {uploadBtn}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 3 }}>📝 视频提示词</div>
          <textarea style={{ width: '100%', height: 100, fontSize: 13, fontFamily: 'monospace', background: 'var(--surface2)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 4, padding: 6, resize: 'vertical', lineHeight: 1.5 }}
            defaultValue={videoPrompt}
            onChange={e => { shotPromptValues.current[si] = e.target.value }} />
          <button style={{ fontSize: 12, color: '#fff', background: 'var(--accent)', border: 'none', borderRadius: 4, padding: '4px 12px', cursor: 'pointer', marginTop: 4 }} onClick={() => handleShotRegen(si)}>✏️ 用修改后的提示词重新生成</button>
        </div>
      </div>
    )
  }

  // ---- 镜头视频卡片 ----
  const renderShotVideo = (v: any) => {
    const si = v.shot_index
    const videoSrc = v.local_file ? `/dramas/${store.currentId}/videos/${v.local_file}` : (v.video_url || '')

    if (v.status === 'completed' && videoSrc) {
      const checked = store.mergeSelected.includes(si)
      return (
        <div key={si} style={{ background: 'var(--bg)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', padding: 12, marginBottom: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>
              <label style={{ cursor: 'pointer', marginRight: 6 }} title="勾选加入合并列表">
                <input type="checkbox" checked={checked} style={{ cursor: 'pointer', width: 15, height: 15, verticalAlign: 'middle' }}
                  onChange={() => store.setMergeSelected(checked ? store.mergeSelected.filter(x => x !== si) : [...store.mergeSelected, si])} />
              </label>
              镜头 {si} <span style={{ color: 'var(--success)', fontSize: 11 }}>✓ 完成</span>
            </span>
            <button style={{ fontSize: 11, color: '#fff', background: 'var(--accent)', border: 'none', borderRadius: 4, padding: '2px 10px', cursor: 'pointer' }} onClick={() => handleShotRegen(si)}>🔄 重新生成</button>
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <div style={{ flexShrink: 0 }}><video src={videoSrc} style={{ width: '100%', maxWidth: 360, borderRadius: 'var(--radius-sm)' }} controls /></div>
            {renderInfoPanel(v)}
          </div>
        </div>
      )
    }
    if (v.status === 'failed') {
      return (
        <div key={si} style={{ background: 'var(--bg)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', padding: 12, marginBottom: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>镜头 {si} <span style={{ color: 'var(--error)', fontSize: 11 }}>✗ 失败</span></span>
            <button style={{ fontSize: 11, color: '#fff', background: 'var(--error)', border: 'none', borderRadius: 4, padding: '2px 10px', cursor: 'pointer' }} onClick={() => handleShotRegen(si)}>🔄 重新生成</button>
          </div>
          <div style={{ fontSize: 11, color: 'var(--error)', marginBottom: 8 }}>{v.error || ''}</div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>{renderInfoPanel(v)}</div>
        </div>
      )
    }
    if (v.status === 'generating') {
      return (
        <div key={si} style={{ background: 'var(--bg)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', padding: 12, marginBottom: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>镜头 {si} <span style={{ color: 'var(--accent)', fontSize: 11 }}>⟳ 视频生成中...</span></div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8 }}>
            <div style={{ flexShrink: 0 }}>
              <div style={{ width: 360, height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--surface2)', borderRadius: 'var(--radius-sm)' }}>
                <span className="loading-spinner" style={{ marginRight: 8 }} /><span style={{ color: 'var(--text2)', fontSize: 13 }}>正在生成视频，请耐心等待...</span>
              </div>
            </div>
            {renderInfoPanel(v)}
          </div>
        </div>
      )
    }
    return (
      <div key={si} style={{ background: 'var(--bg)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', padding: 12, marginBottom: 8 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>镜头 {si} <span style={{ color: 'var(--text2)', fontSize: 11 }}>⏳ 待生成</span></span>
          <button style={{ fontSize: 12, color: '#fff', background: 'var(--success)', border: 'none', borderRadius: 4, padding: '4px 14px', cursor: 'pointer', fontWeight: 600 }} onClick={() => handleShotStart(si)}>▶ 生成视频</button>
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>{renderInfoPanel(v)}</div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card-header"><span style={{ fontSize: 20 }}>🎭</span> 短剧生成</div>
      <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 16 }}>
        输入描述，自动完成 5 步流水线：① 生成故事+剧本 → ② 拆分分镜 → ③ 提取素材并生成三视图 → ④ 逐镜头生成视频 → ⑤ 拼接完整视频
      </p>

      <div className="form-group">
        <label className="form-label">短剧描述</label>
        <textarea className="form-textarea" value={prompt} onChange={e => setPrompt(e.target.value)}
          placeholder="描述你想要的短剧内容..." style={{ minHeight: 120 }} />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label className="form-label">每个分镜时长</label>
          <select className="form-select" value={shotDuration} onChange={e => setShotDuration(Number(e.target.value))}>
            <option value={5}>5 秒 (121帧)</option>
            <option value={10}>10 秒 (241帧)</option>
            <option value={18}>18 秒 (441帧)</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">文本模型</label>
          <select className="form-select" value={textModel} onChange={e => setTextModel(e.target.value)}>
            {models && Object.entries(models.text_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label className="form-label">生图模型</label>
          <select className="form-select" value={imageModel} onChange={e => setImageModel(e.target.value)}>
            {models && Object.entries(models.image_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">视频模型</label>
          <select className="form-select" value={videoModel} onChange={e => setVideoModel(e.target.value)}>
            {models && Object.entries(models.video_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label className="form-label">🎨 角色风格</label>
          <select className="form-select" value={charStyle} onChange={e => setCharStyle(e.target.value)}>
            <option value="anime">动漫卡通</option>
            <option value="realistic">写实真人</option>
            <option value="pixar3d">皮克斯3D</option>
            <option value="semi_realistic">半写实插画</option>
            <option value="watercolor">水彩手绘</option>
            <option value="ink">中国水墨</option>
          </select>
        </div>
      </div>

      <button className="btn btn-primary" onClick={handleStart} disabled={starting}>
        {starting ? <><span className="loading-spinner" /> 启动中...</> : '🎭 开始生成短剧'}
      </button>

      {store.currentId && (
        <>
          <div style={{ marginTop: 20 }}>
            <div className="card" style={{ background: 'var(--surface2)' }}>
              <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>📊 流水线进度</span>
                {store.polling && <button onClick={handleStop} style={{ fontSize: 12, color: '#fff', background: 'var(--error)', border: 'none', borderRadius: 4, padding: '4px 12px', cursor: 'pointer' }}>⏹ 停止</button>}
              </div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                <span className="task-status" style={{ background: '#dbeafe', color: '#1d4ed8' }}>{d ? stepLabels[d.status] || d.status : '等待中'}</span>
                <span style={{ fontSize: 13, color: 'var(--text2)' }}>{d?.message || ''}</span>
              </div>
              <div style={{ background: 'var(--border)', borderRadius: 4, height: 6, overflow: 'hidden' }}>
                <div style={{ width: `${progress}%`, height: '100%', background: barColor, transition: 'width 0.5s' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 11, color: 'var(--text2)' }}>
                <span>① 故事+剧本</span><span>② 分镜</span><span>③ 三视图</span><span>④ 视频</span><span>⑤ 拼接</span>
              </div>
            </div>
          </div>

          {/* 故事 */}
          {d?.story && (
            <div style={{ marginTop: 16 }}>
              <div className="card" style={{ background: 'var(--surface2)' }}>
                <div className="card-header">📖 故事梗概</div>
                <pre style={{ fontSize: 13, whiteSpace: 'pre-wrap', lineHeight: 1.7, maxHeight: 250, overflow: 'auto', background: 'var(--bg)', padding: 12, borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>{d.story}</pre>
                {d.status === 'paused_story' && !store.storyConfirmed && (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--accent)' }}>✏️ 编辑故事梗概（修改后将影响后续剧本和分镜）</div>
                    <textarea style={{ width: '100%', minHeight: 150, fontSize: 13, lineHeight: 1.7, background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--accent)', borderRadius: 'var(--radius-sm)', padding: 10, resize: 'vertical' }}
                      value={storyEdit} onChange={e => setStoryEdit(e.target.value)} />
                    <div style={{ display: 'flex', gap: 10, marginTop: 8, justifyContent: 'flex-end' }}>
                      <button className="btn btn-primary" onClick={() => handleStoryConfirm(storyEdit)}>✏️ 使用修改后的故事继续</button>
                      <button className="btn" onClick={() => handleStoryConfirm()}>✅ 使用原故事继续</button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 剧本 */}
          {d?.script && (
            <div style={{ marginTop: 16 }}>
              <div className="card" style={{ background: 'var(--surface2)' }}>
                <div className="card-header">📝 剧本</div>
                <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto', background: 'var(--bg)', padding: 12, borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
                  {typeof d.script === 'string' ? d.script : JSON.stringify(d.script, null, 2)}
                </pre>
              </div>
            </div>
          )}

          {/* 分镜 */}
          {d?.storyboard?.shots && (
            <div style={{ marginTop: 16 }}>
              <div className="card" style={{ background: 'var(--surface2)' }}>
                <div className="card-header">🎬 分镜脚本</div>
                {d.storyboard.shots.map((s: any) => (
                  <div key={s.shot_index} style={{ padding: 10, background: 'var(--bg)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', marginBottom: 8 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>镜头 {s.shot_index} <span style={{ color: 'var(--text2)', fontWeight: 400 }}>[{s.camera || ''}]</span></div>
                    <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 4 }}>{s.scene_desc || ''}</div>
                    <div style={{ fontSize: 11, color: 'var(--accent)', marginTop: 4, fontFamily: 'monospace' }}>{(s.prompt_en || '').substring(0, 120)}...</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 素材三视图 */}
          {d?.assets?.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div className="card" style={{ background: 'var(--surface2)' }}>
                <div className="card-header">🖼 三视图参考图</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
                  {d.assets.map(renderAsset)}
                </div>
              </div>
            </div>
          )}

          {/* 确认参考图 */}
          {d?.status === 'paused' && (
            <div style={{ marginTop: 12, background: 'linear-gradient(135deg, #f39c12, #e67e22)', borderRadius: 'var(--radius)', padding: 16, textAlign: 'center' }}>
              <div style={{ fontSize: 14, color: '#fff', marginBottom: 12 }}>⏸ 流水线已暂停 — 请检查参考图，如需替换可点击卡片上的「替换」按钮</div>
              <button className="btn btn-primary" style={{ background: '#fff', color: '#e67e22', fontWeight: 700, padding: '10px 32px' }} onClick={handleResume}>✅ 确认参考图</button>
            </div>
          )}

          {/* 生成视频 */}
          {d?.video_results?.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div className="card" style={{ background: 'var(--surface2)' }}>
                <div className="card-header">🎥 生成视频</div>

                {/* 完整合并视频 */}
                {d.merged_video && (
                  <div style={{ background: 'linear-gradient(135deg, var(--accent) 0%, #6c5ce7 100%)', borderRadius: 'var(--radius-sm)', padding: 16, marginBottom: 12 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', marginBottom: 10 }}>🎬 完整视频（已合并）</div>
                    <video src={`/dramas/${store.currentId}/videos/${d.merged_video}`} style={{ width: '100%', maxWidth: 600, borderRadius: 'var(--radius-sm)' }} controls />
                  </div>
                )}
                {d.status === 'merging' && (
                  <div style={{ background: 'var(--bg)', borderRadius: 'var(--radius-sm)', padding: 16, marginBottom: 12, border: '1px dashed var(--accent)' }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--accent)' }}>🎬 正在拼接完整视频... <span className="loading-spinner" style={{ marginLeft: 6 }} /></div>
                  </div>
                )}

                {d.video_results.map(renderShotVideo)}
              </div>
            </div>
          )}

          {/* 自定义合并 */}
          {d?.video_results?.some((v: any) => v.status === 'completed' && v.local_file) && (
            <div style={{ marginTop: 16 }}>
              <div className="card" style={{ background: 'var(--surface2)' }}>
                <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>🎬 自定义合并</span>
                  <span style={{ fontSize: 11, color: 'var(--text2)' }}>勾选镜头并排序，可多次合并不同组合</span>
                </div>
                <div style={{ padding: 12 }}>
                  <div style={{ minHeight: 36, marginBottom: 10, padding: 8, background: 'var(--bg)', borderRadius: 'var(--radius-sm)', border: '1px dashed var(--border)' }}>
                    {store.mergeSelected.length === 0 ? (
                      <span style={{ fontSize: 11, color: 'var(--text2)' }}>未选择镜头，请在下方视频中勾选</span>
                    ) : (
                      <>
                        <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4 }}>合并顺序 ({store.mergeSelected.length} 个镜头):</div>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                          {store.mergeSelected.map((si, idx) => (
                            <span key={si} style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 2, background: 'var(--surface2)', borderRadius: 4, padding: '3px 6px', border: '1px solid var(--border)' }}>
                                <span style={{ fontSize: 11, fontWeight: 600 }}>镜头{si}</span>
                                {idx > 0 && <button onClick={() => moveMergeShot(idx, -1)} style={{ fontSize: 10, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', padding: '0 2px' }} title="左移">◀</button>}
                                {idx < store.mergeSelected.length - 1 && <button onClick={() => moveMergeShot(idx, 1)} style={{ fontSize: 10, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', padding: '0 2px' }} title="右移">▶</button>}
                                <button onClick={() => removeMergeShot(idx)} style={{ fontSize: 10, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--error)', padding: '0 2px' }} title="移除">✕</button>
                              </div>
                              {idx < store.mergeSelected.length - 1 && <span style={{ color: 'var(--text2)', fontSize: 10 }}>→</span>}
                            </span>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <input className="form-input" placeholder="合并名称(可选)" value={mergeName} onChange={e => setMergeName(e.target.value)} style={{ flex: 1, minWidth: 120, fontSize: 12 }} />
                    <button className="btn btn-primary" style={{ padding: '6px 16px', fontSize: 12 }} onClick={doMerge}>🎬 合并选中镜头</button>
                    <button style={{ padding: '6px 12px', fontSize: 11, color: 'var(--text2)', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', cursor: 'pointer' }} onClick={() => store.clearMergeSelection()}>清空选择</button>
                  </div>

                  {d.custom_merges?.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      {d.custom_merges.map((m: any, mi: number) => {
                        const videoSrc = `/dramas/${store.currentId}/videos/${m.merged_file}`
                        return (
                          <div key={mi} style={{ background: 'var(--bg)', borderRadius: 'var(--radius-sm)', padding: 10, marginTop: 8, border: '1px solid var(--border)' }}>
                            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>🎬 {m.name} (镜头: {m.shot_indices.join(' → ')})</div>
                            <video src={videoSrc} style={{ width: '100%', maxWidth: 500, borderRadius: 'var(--radius-sm)' }} controls />
                            <a href={videoSrc} download style={{ fontSize: 11, color: 'var(--accent)', marginTop: 4, display: 'inline-block' }}>⬇️ 下载</a>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}