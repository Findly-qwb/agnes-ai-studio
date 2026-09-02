// 节点编辑抽屉：按节点类型渲染不同的编辑面板
import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useToast } from '../../store/useToast'
import { useModels } from '../../store/useModels'
import { EnhanceBtn } from '../EnhanceBtn'

const btn = { fontSize: 12, color: '#fff', background: 'var(--accent)', border: 'none', borderRadius: 4, padding: '4px 12px', cursor: 'pointer' } as const
const btnSm = { ...btn, padding: '2px 8px', fontSize: 11 } as const
const ta = { width: '100%', background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 6, padding: 8, fontSize: 12, fontFamily: 'inherit', resize: 'vertical' as const }

// 通用 loading 按钮：onClick 返回 Promise，执行期间 ⏳ + 禁用，防重复点击
export function AsyncBtn({ onClick, children, style, disabled, ...rest }: any) {
  const [busy, setBusy] = useState(false)
  const off = disabled || busy
  return (
    <button {...rest} disabled={off} style={{ ...style, opacity: off ? 0.6 : 1, cursor: off ? 'default' : 'pointer' }}
      onClick={async e => {
        if (busy) return
        setBusy(true)
        try { await onClick(e) } finally { setBusy(false) }
      }}>
      {busy ? '⏳ ' : ''}{children}
    </button>
  )
}

// 文件上传 label 版：同样带 loading
export function AsyncFileLabel({ children, onFile, style, ...rest }: { children: any, onFile: (f: File) => Promise<unknown>, style?: any, [k: string]: unknown }) {
  const [busy, setBusy] = useState(false)
  return (
    <label style={{ ...style, opacity: busy ? 0.6 : 1 }}>
      {busy ? '⏳ ' : ''}{children}
      <input type="file" {...rest} disabled={busy}
        style={{ display: 'none' }}
        onChange={async e => {
          const f = e.target.files?.[0]
          if (!f) return
          setBusy(true)
          try { await onFile(f) } finally { setBusy(false); e.target.value = '' }
        }} />
    </label>
  )
}

// 内容未产出占位：运行中不渲染空编辑器，避免误编辑后被回填覆盖
function LoadingBox({ label }: { label: string }) {
  return (
    <div style={{ minHeight: 140, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, color: 'var(--text2)', fontSize: 12, border: '1px dashed var(--border)', borderRadius: 8 }}>
      <span className="loading-spinner" style={{ width: 22, height: 22 }} />
      {label}
    </div>
  )
}

// ---------- 描述节点（prompt） ----------
export function PromptEditor({ flow, onSaved }: { flow: any, onSaved: () => void }) {
  const say = useToast().show
  const [p, setP] = useState(flow.params?.prompt || '')
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 6 }}>短剧描述（保存后此节点及下游自动标记「需重跑」，点运行即整链重新生成）</div>
      <textarea style={{ ...ta, minHeight: 160 }} value={p} onChange={e => setP(e.target.value)} />
      <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <EnhanceBtn getText={() => p} mode="story" onApply={setP} />
        <AsyncBtn style={{ ...btn, marginLeft: 'auto' }} onClick={async () => {
          try {
            await api.flowSaveGraph(flow.flow_id, { params: { ...flow.params, prompt: p } })
            say('描述已保存', 'success')
            onSaved()
          } catch (e: any) { say('保存失败: ' + e.message, 'error') }
        }}>💾 保存描述</AsyncBtn>
      </div>
    </div>
  )
}

// ---------- 文本节点（故事/剧本） ----------
export function TextEditor({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  const say = useToast().show
  const [text, setText] = useState(node.output?.text || '')
  if (node.status === 'running') return <LoadingBox label="内容生成中，完成后可编辑…" />
  return (
    <div>
      <textarea style={{ ...ta, minHeight: 260, lineHeight: 1.7 }} value={text} onChange={e => setText(e.target.value)} />
      <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <EnhanceBtn getText={() => text} mode="story" onApply={setText} />
        <AsyncBtn style={{ ...btn, marginLeft: 'auto' }} onClick={async () => {
          try {
            await api.flowNodeEdit(flow.flow_id, node.id, { output: { text } })
            say('已保存，下游节点标记为需重跑', 'success')
            onSaved()
          } catch (e: any) { say('保存失败: ' + e.message, 'error') }
        }}>💾 保存修改</AsyncBtn>
      </div>
    </div>
  )
}

// ---------- 分镜 JSON 节点 ----------
export function StoryboardEditor({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  const say = useToast().show
  const [json, setJson] = useState(JSON.stringify(node.output?.shots || [], null, 1))
  if (node.status === 'running') return <LoadingBox label="分镜生成中（含 LLM 自审修复），完成后可直接编辑 JSON…" />
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 6 }}>直接编辑分镜 JSON（shot_index / scene_desc / characters / action / camera / dialogue / prompt_en）</div>
      <textarea style={{ ...ta, minHeight: 320, fontFamily: 'monospace' }} value={json} onChange={e => setJson(e.target.value)} />
      <div style={{ marginTop: 8, textAlign: 'right' }}>
        <AsyncBtn style={btn} onClick={async () => {
          try {
            const shots = JSON.parse(json)
            if (!Array.isArray(shots)) throw new Error('需要是 shots 数组')
            await api.flowNodeEdit(flow.flow_id, node.id, { output: { shots } })
            say('分镜已保存', 'success')
            onSaved()
          } catch (e: any) { say('JSON 错误: ' + e.message, 'error') }
        }}>💾 保存分镜</AsyncBtn>
      </div>
    </div>
  )
}

// ---------- 素材节点 ----------
export function AssetsEditor({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  const say = useToast().show
  const assets: any[] = node.output?.assets || []
  const running = node.status === 'running'
  const descEdits = useRef<Record<number, string>>({})
  const descRefs = useRef<Record<number, HTMLTextAreaElement | null>>({})

  const imgSrc = (a: any) => a.local_file ? `/dramas/${flow.drama_id}/images/${a.local_file}` : (a.image_url || '')
  const catLabel: Record<string, string> = { characters: '角色', scenes: '场景', props: '道具' }

  if (!assets.length) {
    return running
      ? <LoadingBox label="剧本解析 + 素材生图中：先提取角色/场景/道具清单，再逐个出三视图…" />
      : <div style={{ fontSize: 12, color: 'var(--text2)' }}>素材未生成：点「▶ 运行此节点」开始</div>
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: 10 }}>
      {assets.map((a, idx) => (
        <div key={idx} style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
          {imgSrc(a)
            ? <img src={imgSrc(a)} title="点击查看原图" style={{ width: '100%', height: 'auto', maxHeight: 320, objectFit: 'contain', background: '#fff', cursor: 'zoom-in' }}
                onClick={() => window.open(imgSrc(a), '_blank')} />
            : <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: running ? 'var(--text2)' : 'var(--error)', fontSize: 12 }}>
                {running ? <><span className="loading-spinner" /> 生成中…</> : (a.error ? String(a.error).slice(0, 60) : '生成失败')}
              </div>}
          <div style={{ padding: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
              {a.name} <span style={{ color: 'var(--accent)', fontSize: 10 }}>[{catLabel[a.category] || a.category}]</span>
            </div>
            <textarea style={{ ...ta, minHeight: 60, fontSize: 11 }} defaultValue={a.desc || ''}
              ref={el => { descRefs.current[idx] = el }}
              onChange={e => { descEdits.current[idx] = e.target.value }} />
            <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap', alignItems: 'flex-start' }}>
              <EnhanceBtn getText={() => descEdits.current[idx] ?? a.desc ?? a.img_prompt ?? ''} mode="image"
                onApply={t => { descEdits.current[idx] = t; if (descRefs.current[idx]) descRefs.current[idx].value = t }} />
              <AsyncBtn style={btnSm} onClick={async () => {
                try {
                  const custom = descEdits.current[idx]
                  await api.flowAssetRegenerate(flow.flow_id, { asset_index: idx, ...(custom ? { custom_desc: custom } : {}) })
                  say('已重新生成', 'success')
                  onSaved()
                } catch (e: any) { say('失败: ' + e.message, 'error') }
              }}>🔄 重新生成</AsyncBtn>
              <AsyncFileLabel accept="image/*" style={{ ...btnSm, display: 'inline-block' }} onFile={async f => {
                try {
                  await api.flowAssetReplace(flow.flow_id, idx, f)
                  say('已替换', 'success')
                  onSaved()
                } catch (err: any) { say('替换失败: ' + err.message, 'error') }
              }}>⬆️ 替换</AsyncFileLabel>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------- 镜头视频节点 ----------
// 按连线向上找最近一个有输出的指定类型祖先（与后端 _upstream_outputs 语义一致）
function nearestAncestor(flow: any, nodeId: string, type: string): any {
  const parents: Record<string, string[]> = {}
  for (const e of flow.edges || []) { (parents[e.target] ||= []).push(e.source) }
  const q = [...(parents[nodeId] || [])]
  const seen = new Set<string>()
  while (q.length) {
    const cur = q.shift()!
    if (seen.has(cur)) continue
    seen.add(cur)
    const n = flow.nodes?.[cur]
    if (n?.type === type && n.output) return n
    q.push(...(parents[cur] || []))
  }
  return null
}

export function ShotsEditor({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  const say = useToast().show
  const sb = nearestAncestor(flow, node.id, 'storyboard')
  const shots: any[] = sb?.output?.shots || []
  const results: any[] = node.output?.results || []
  const [open, setOpen] = useState<number | null>(null)

  const runShot = async (si: number, extra?: any) => {
    try {
      await api.flowShotRun(flow.flow_id, { shot_index: si, ...(extra || {}) })
      say(`镜头 ${si} 开始生成`, 'success')
      setOpen(si)   // 生成即展开详情：参考图/提示词不用二次点击
      onSaved()
    } catch (e: any) { say('启动失败: ' + e.message, 'error') }
  }

  return (
    <div>
      {shots.map((s: any) => {
        const r = results.find(x => x.shot_index === s.shot_index)
        const si = s.shot_index
        const videoSrc = r?.local_file ? `/dramas/${flow.drama_id}/videos/${r.local_file}` : ''
        const expanded = open === si
        return (
          <div key={si} style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, padding: 10, marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 600, cursor: 'pointer', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} onClick={() => setOpen(expanded ? null : si)}>
                镜头 {si} <span style={{ fontSize: 11, color: 'var(--text2)', fontWeight: 400 }}>[{s.camera || ''}] {String(s.scene_desc || '').slice(0, 40)}</span>
              </span>
              <span style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0, whiteSpace: 'nowrap' }}>
                {r?.status === 'completed' && <span style={{ fontSize: 11, color: 'var(--success)' }}>✓ 完成</span>}
                {r?.status === 'generating' && <span style={{ fontSize: 11, color: '#3b82f6', display: 'flex', alignItems: 'center', gap: 4 }}><span className="loading-spinner" style={{ width: 11, height: 11 }} /> 生成中…</span>}
                {r?.status === 'failed' && <span style={{ fontSize: 11, color: 'var(--error)', maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis' }} title={r.error}>✗ {String(r.error || '').slice(0, 40)}</span>}
                {!r && node.status === 'running' && <span style={{ fontSize: 11, color: 'var(--text2)', display: 'flex', alignItems: 'center', gap: 4 }}><span className="loading-spinner" style={{ width: 11, height: 11 }} /> 排队中</span>}
                {(!r || r.status !== 'generating') && node.status !== 'running' && (
                  <AsyncBtn style={btnSm} onClick={() => runShot(si)}>{r?.status === 'completed' ? '🔄 重做' : '▶ 生成'}</AsyncBtn>
                )}
              </span>
            </div>
            {videoSrc && <video src={videoSrc} controls style={{ display: 'block', margin: '8px auto 0', height: 220, maxWidth: '100%', borderRadius: 6, background: '#000' }} />}
            {!videoSrc && r?.status === 'generating' && (
              <div style={{ height: 160, display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center', justifyContent: 'center', background: 'var(--surface2)', borderRadius: 6, marginTop: 8, color: 'var(--text2)', fontSize: 12 }}>
                <span className="loading-spinner" /> 正在生成视频，请耐心等待…
              </div>
            )}
            {expanded && <ShotDetail flow={flow} shotIndex={si} say={say} onSaved={onSaved} runShot={runShot} />}
          </div>
        )
      })}
      {shots.length === 0 && <div style={{ color: 'var(--text2)', fontSize: 12 }}>
        {(flow.edges || []).some((e: any) => e.target === node.id)
          ? '上游分镜尚未生成，请先运行分镜节点'
          : '该节点还没有输入连线：从「分镜」节点右侧圆点拉一条线过来'}
      </div>}
    </div>
  )
}

function ShotDetail({ flow, shotIndex, say, onSaved, runShot }: any) {
  const [detail, setDetail] = useState<any>(null)
  const [prompt, setPrompt] = useState('')
  useEffect(() => {
    api.flowShotDetail(flow.flow_id, shotIndex).then(d => {
      setDetail(d)
      setPrompt(d.custom_prompt || d.result?.prompt_cn || d.result?.prompt || '')
    }).catch(() => { })
  }, [shotIndex, flow.flow_id])
  if (!detail) return <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 8 }}>加载镜头详情…</div>
  const refs = detail.custom_images.length ? detail.custom_images : detail.auto_refs
  return (
    <div style={{ marginTop: 10, borderTop: '1px dashed var(--border)', paddingTop: 8 }}>
      <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4 }}>
        参考图（{detail.custom_images.length ? '自定义' : '自动匹配'}）
        <AsyncFileLabel accept="image/*" style={{ marginLeft: 8, color: 'var(--accent)', cursor: 'pointer', fontWeight: 400 }}
          onFile={async f => {
            try { await api.flowShotImageUpload(flow.flow_id, shotIndex, f); say('参考图已上传', 'success'); onSaved() }
            catch (err: any) { say('上传失败: ' + err.message, 'error') }
          }}>+ 上传</AsyncFileLabel>
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {refs.map((img: any, i: number) => (
          <div key={i} style={{ position: 'relative' }}>
            <img src={img.local_file ? `/dramas/${flow.drama_id}/images/${img.local_file}` : img.image_url}
              style={{ width: 52, height: 52, objectFit: 'cover', borderRadius: 4, border: '1px solid var(--border)' }} />
            {detail.custom_images.length > 0 && (
              <AsyncBtn onClick={async () => {
                try {
                  await api.flowShotImageDelete(flow.flow_id, { shot_index: shotIndex, image_index: i })
                  onSaved()
                } catch (err: any) { say('删除失败: ' + err.message, 'error') }
              }} style={{ position: 'absolute', top: -5, right: -5, width: 15, height: 15, borderRadius: '50%', background: 'var(--error)', color: '#fff', border: 'none', fontSize: 9, padding: 0, lineHeight: 1 }}>✕</AsyncBtn>
            )}
          </div>
        ))}
      </div>
      <div style={{ fontSize: 11, fontWeight: 600, margin: '8px 0 4px' }}>视频提示词（中文会自动翻译）</div>
      <textarea style={{ ...ta, minHeight: 80, fontSize: 12 }} value={prompt} onChange={e => setPrompt(e.target.value)} />
      <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <AsyncBtn style={{ ...btnSm, marginTop: 6 }} onClick={() => runShot(shotIndex, prompt ? { custom_prompt: prompt } : {})}>
          ▶ 用此提示词生成
        </AsyncBtn>
        <EnhanceBtn getText={() => prompt} mode="video" onApply={setPrompt} />
      </div>
    </div>
  )
}

// ---------- 合并节点 ----------
export function MergeEditor({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  const say = useToast().show
  const sh = nearestAncestor(flow, node.id, 'shots')
  const results: any[] = sh?.output?.results || []
  const done = results.filter(r => r.status === 'completed' && r.local_file)
  // 默认全选按序合并（最常见意图），再手动增删/调序
  const [order, setOrder] = useState<number[]>(() => done.map(d => d.shot_index))
  const [name, setName] = useState('')

  const toggle = (si: number) => setOrder(o => o.includes(si) ? o.filter(x => x !== si) : [...o, si])
  const move = (i: number, dir: number) => setOrder(o => {
    const n = [...o]; const j = i + dir
    if (j < 0 || j >= n.length) return o
    ;[n[i], n[j]] = [n[j], n[i]]
    return n
  })
  const mergedList = [...(flow.custom_merges || []), ...(flow.merged_video ? [{ name: '流水线合并', merged_file: flow.merged_video, shot_indices: [] }] : [])]

  return (
    <div>
      {node.status === 'running' && (
        <div style={{ background: 'var(--bg)', borderRadius: 6, padding: 12, marginBottom: 8, border: '1px dashed var(--accent)', fontSize: 13, color: 'var(--accent)', display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className="loading-spinner" /> 🎬 正在拼接完整视频，通常需要几十秒…
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12, marginBottom: 8, gap: 8 }}>
        <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>已完成的镜头：{done.map(d => `#${d.shot_index}`).join(', ') || '无'}</span>
        <span style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
          <button style={btnSm} onClick={() => setOrder(done.map(d => d.shot_index))}>全选</button>
          <button style={btnSm} onClick={() => setOrder([])}>清空</button>
        </span>
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
        {done.map(d => (
          <label key={d.shot_index} style={{
            fontSize: 11, padding: '3px 10px', borderRadius: 6, cursor: 'pointer',
            border: `1px solid ${order.includes(d.shot_index) ? 'var(--accent)' : 'var(--border)'}`,
            background: order.includes(d.shot_index) ? 'rgba(99,102,241,.15)' : 'var(--bg)',
          }}>
            <input type="checkbox" checked={order.includes(d.shot_index)} onChange={() => toggle(d.shot_index)} style={{ marginRight: 4 }} />
            镜头{d.shot_index}
          </label>
        ))}
      </div>
      {order.length > 0 && (
        <div style={{ fontSize: 11, marginBottom: 8, padding: 6, background: 'var(--bg)', borderRadius: 6 }}>
          合并顺序：{order.map((si, i) => (
            <span key={si}>
              <b>#{si}</b>
              <button onClick={() => move(i, -1)} style={{ border: 'none', background: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 10 }}>◀</button>
              <button onClick={() => move(i, 1)} style={{ border: 'none', background: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 10 }}>▶</button>
              {i < order.length - 1 && ' → '}
            </span>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', gap: 8 }}>
        <input className="form-input" placeholder="合并名称(可选)" value={name} onChange={e => setName(e.target.value)} style={{ flex: 1, fontSize: 12 }} />
        <AsyncBtn style={btn} disabled={order.length < 2} onClick={async () => {
          try {
            const d = await api.flowMerge(flow.flow_id, { shot_indices: order, merge_name: name.trim() || `merge_${Date.now() % 10000}`, node_id: node.id })
            say(d.pipeline_completed ? '合并成功 · 全部镜头已收口，流水线完成 ✅' : '合并成功！', 'success')
            setOrder([])
            onSaved()
          } catch (e: any) { say('合并失败: ' + e.message, 'error') }
        }}>🧩 合并</AsyncBtn>
      </div>
      {mergedList.map((m: any, i: number) => {
        const pipeline = !m.shot_indices?.length
        return (
          <div key={i} style={{ marginTop: 12, background: pipeline ? 'linear-gradient(135deg, var(--accent) 0%, #6c5ce7 100%)' : 'var(--bg)', border: pipeline ? 'none' : '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: pipeline ? '#fff' : 'var(--text)' }}>🎬 {m.name}{m.shot_indices?.length ? `（${m.shot_indices.join(' → ')}）` : ''}</div>
            <video src={`/dramas/${flow.drama_id}/videos/${m.merged_file}`} controls style={{ width: '100%', maxWidth: 460, borderRadius: 6 }} />
            <a href={`/dramas/${flow.drama_id}/videos/${m.merged_file}`} download style={{ fontSize: 11, color: pipeline ? '#fff' : 'var(--accent)', display: 'inline-block', marginTop: 4 }}>⬇️ 下载</a>
          </div>
        )
      })}
    </div>
  )
}

// ---------- 节点级参数覆盖（ComfyUI 式 widget，默认继承流参数） ----------
export const STYLE_LABELS: Record<string, string> = {
  anime: '动漫卡通', realistic: '写实真人', pixar3d: '皮克斯3D',
  semi_realistic: '半写实插画', watercolor: '水彩手绘', ink: '中国水墨',
}

export function NodeParams({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  const models = useModels()
  const say = useToast().show
  const [p, setP] = useState<Record<string, string>>(() => {
    const src: Record<string, string> = {}
    for (const [k, v] of Object.entries(node.params || {})) if (v) src[k] = String(v)
    return src
  })
  if (!models) return null
  const type: string = node.type
  const dur: [string, string][] = [['5', '5 秒/镜'], ['10', '10 秒/镜'], ['18', '18 秒/镜']]
  const fields: { key: string; label: string; opts: [string, string][] }[] = []
  if (['story', 'script'].includes(type)) fields.push({ key: 'text_model', label: '文本模型', opts: Object.entries(models.text_models) })
  if (type === 'storyboard') {
    fields.push({ key: 'text_model', label: '文本模型', opts: Object.entries(models.text_models) })
    fields.push({ key: 'shot_duration', label: '镜头时长', opts: dur })
  }
  if (type === 'assets') {
    fields.push({ key: 'text_model', label: '提取模型', opts: Object.entries(models.text_models) })
    fields.push({ key: 'image_model', label: '图片模型', opts: Object.entries(models.image_models) })
    fields.push({ key: 'character_style', label: '画面风格', opts: Object.entries(STYLE_LABELS) })
  }
  if (type === 'shots') {
    fields.push({ key: 'video_model', label: '视频模型', opts: Object.entries(models.video_models) })
    fields.push({ key: 'shot_duration', label: '镜头时长', opts: dur })
    fields.push({ key: 'text_model', label: '翻译模型', opts: Object.entries(models.text_models) })
    fields.push({ key: 'shot_workers', label: '并发数', opts: [['1', '1'], ['2', '2'], ['3', '3'], ['4', '4']] as [string, string][] })
  }
  if (!fields.length) return null
  const inheritName = (key: string) => {
    const v = flow.params?.[key]
    const all: Record<string, string> = { ...models.text_models, ...models.image_models, ...models.video_models, ...STYLE_LABELS }
    return all[v] || v || '未设置'
  }
  // 改完即存（ComfyUI widget 语义）：避免「选了模型没点保存 → 运行用旧模型」的陷阱
  const change = (key: string, v: string) => {
    const n = { ...p }
    if (v) n[key] = v
    else delete n[key]
    setP(n)
    api.flowNodeParams(flow.flow_id, node.id, n).then(onSaved).catch(e => say('保存失败: ' + e.message, 'error'))
  }
  return (
    <div style={{ border: '1px dashed var(--border)', borderRadius: 8, padding: 8, marginBottom: 10 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text2)', marginBottom: 6 }}>⚙ 节点参数（改动即时自动保存 · 默认继承流配置）</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {fields.map(f => (
          <label key={f.key} style={{ fontSize: 11, color: 'var(--text2)' }}>
            {f.label}
            <select className="form-select" style={{ width: '100%', marginTop: 2, fontSize: 12 }}
              value={p[f.key] || ''}
              onChange={e => change(f.key, e.target.value)}>
              <option value="">继承：{inheritName(f.key)}</option>
              {f.opts.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        ))}
      </div>
    </div>
  )
}
