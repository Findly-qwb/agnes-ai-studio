// 节点编辑抽屉：按节点类型渲染不同的编辑面板
import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useToast } from '../../store/useToast'

const btn = { fontSize: 12, color: '#fff', background: 'var(--accent)', border: 'none', borderRadius: 4, padding: '4px 12px', cursor: 'pointer' } as const
const btnSm = { ...btn, padding: '2px 8px', fontSize: 11 } as const
const ta = { width: '100%', background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 6, padding: 8, fontSize: 12, fontFamily: 'inherit', resize: 'vertical' as const }

// ---------- 描述节点（prompt） ----------
export function PromptEditor({ flow, onSaved }: { flow: any, onSaved: () => void }) {
  const say = useToast().show
  const [p, setP] = useState(flow.params?.prompt || '')
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 6 }}>短剧描述（保存后需重跑故事及所有下游节点）</div>
      <textarea style={{ ...ta, minHeight: 160 }} value={p} onChange={e => setP(e.target.value)} />
      <div style={{ marginTop: 8, textAlign: 'right' }}>
        <button style={btn} onClick={async () => {
          try {
            await api.flowSaveGraph(flow.flow_id, { params: { ...flow.params, prompt: p } })
            say('描述已保存', 'success')
            onSaved()
          } catch (e: any) { say('保存失败: ' + e.message, 'error') }
        }}>💾 保存描述</button>
      </div>
    </div>
  )
}

// ---------- 文本节点（故事/剧本） ----------
export function TextEditor({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  const say = useToast().show
  const [text, setText] = useState(node.output?.text || '')
  const [saving, setSaving] = useState(false)
  return (
    <div>
      <textarea style={{ ...ta, minHeight: 260, lineHeight: 1.7 }} value={text} onChange={e => setText(e.target.value)} />
      <div style={{ marginTop: 8, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button style={btn} disabled={saving} onClick={async () => {
          setSaving(true)
          try {
            await api.flowNodeEdit(flow.flow_id, node.id, { output: { text } })
            say('已保存，下游节点标记为需重跑', 'success')
            onSaved()
          } catch (e: any) { say('保存失败: ' + e.message, 'error') }
          setSaving(false)
        }}>💾 保存修改</button>
      </div>
    </div>
  )
}

// ---------- 分镜 JSON 节点 ----------
export function StoryboardEditor({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  const say = useToast().show
  const [json, setJson] = useState(JSON.stringify(node.output?.shots || [], null, 1))
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 6 }}>直接编辑分镜 JSON（shot_index / scene_desc / characters / action / camera / dialogue / prompt_en）</div>
      <textarea style={{ ...ta, minHeight: 320, fontFamily: 'monospace' }} value={json} onChange={e => setJson(e.target.value)} />
      <div style={{ marginTop: 8, textAlign: 'right' }}>
        <button style={btn} onClick={async () => {
          try {
            const shots = JSON.parse(json)
            if (!Array.isArray(shots)) throw new Error('需要是 shots 数组')
            await api.flowNodeEdit(flow.flow_id, node.id, { output: { shots } })
            say('分镜已保存', 'success')
            onSaved()
          } catch (e: any) { say('JSON 错误: ' + e.message, 'error') }
        }}>💾 保存分镜</button>
      </div>
    </div>
  )
}

// ---------- 素材节点 ----------
export function AssetsEditor({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  const say = useToast().show
  const assets: any[] = node.output?.assets || []
  const descEdits = useRef<Record<number, string>>({})

  const imgSrc = (a: any) => a.local_file ? `/dramas/${flow.drama_id}/images/${a.local_file}` : (a.image_url || '')
  const catLabel: Record<string, string> = { characters: '角色', scenes: '场景', props: '道具' }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: 10 }}>
      {assets.map((a, idx) => (
        <div key={idx} style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
          {imgSrc(a)
            ? <img src={imgSrc(a)} style={{ width: '100%', height: 140, objectFit: 'cover' }} />
            : <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--error)', fontSize: 12 }}>{a.error ? String(a.error).slice(0, 60) : '生成失败'}</div>}
          <div style={{ padding: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
              {a.name} <span style={{ color: 'var(--accent)', fontSize: 10 }}>[{catLabel[a.category] || a.category}]</span>
            </div>
            <textarea style={{ ...ta, minHeight: 60, fontSize: 11 }} defaultValue={a.desc || ''}
              onChange={e => { descEdits.current[idx] = e.target.value }} />
            <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
              <button style={btnSm} onClick={async () => {
                say('参考图重新生成中…', 'info')
                try {
                  const custom = descEdits.current[idx]
                  await api.flowAssetRegenerate(flow.flow_id, { asset_index: idx, ...(custom ? { custom_desc: custom } : {}) })
                  say('已重新生成', 'success')
                  onSaved()
                } catch (e: any) { say('失败: ' + e.message, 'error') }
              }}>🔄 重新生成</button>
              <label style={{ ...btnSm, display: 'inline-block' }}>
                ⬆️ 替换
                <input type="file" accept="image/*" style={{ display: 'none' }}
                  onChange={async e => {
                    const f = e.target.files?.[0]
                    if (!f) return
                    try {
                      await api.flowAssetReplace(flow.flow_id, idx, f)
                      say('已替换', 'success')
                      onSaved()
                    } catch (err: any) { say('替换失败: ' + err.message, 'error') }
                    e.target.value = ''
                  }} />
              </label>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------- 镜头视频节点 ----------
export function ShotsEditor({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  const say = useToast().show
  const sb = flow.nodes ? Object.values<any>(flow.nodes).find((n: any) => n.type === 'storyboard' && n.output) : null
  const shots: any[] = sb ? sb.output.shots : []
  const results: any[] = node.output?.results || []
  const [open, setOpen] = useState<number | null>(null)

  const runShot = async (si: number, extra?: any) => {
    try {
      await api.flowShotRun(flow.flow_id, { shot_index: si, ...(extra || {}) })
      say(`镜头 ${si} 开始生成`, 'success')
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, fontWeight: 600, cursor: 'pointer' }} onClick={() => setOpen(expanded ? null : si)}>
                镜头 {si} <span style={{ fontSize: 11, color: 'var(--text2)', fontWeight: 400 }}>[{s.camera || ''}] {String(s.scene_desc || '').slice(0, 40)}</span>
              </span>
              <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                {r?.status === 'completed' && <span style={{ fontSize: 11, color: 'var(--success)' }}>✓ 完成</span>}
                {r?.status === 'generating' && <span style={{ fontSize: 11, color: '#3b82f6' }}>⟳ 生成中…</span>}
                {r?.status === 'failed' && <span style={{ fontSize: 11, color: 'var(--error)' }}>✗ {String(r.error || '').slice(0, 40)}</span>}
                {(!r || r.status !== 'generating') && (
                  <button style={btnSm} onClick={() => runShot(si)}>{r?.status === 'completed' ? '🔄 重做' : '▶ 生成'}</button>
                )}
              </span>
            </div>
            {videoSrc && <video src={videoSrc} controls style={{ width: '100%', maxWidth: 420, borderRadius: 6, marginTop: 8 }} />}
            {expanded && <ShotDetail flow={flow} shotIndex={si} say={say} onSaved={onSaved} runShot={runShot} />}
          </div>
        )
      })}
      {shots.length === 0 && <div style={{ color: 'var(--text2)', fontSize: 12 }}>分镜未生成，请先运行分镜节点</div>}
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
        <label style={{ marginLeft: 8, color: 'var(--accent)', cursor: 'pointer', fontWeight: 400 }}>
          + 上传
          <input type="file" accept="image/*" style={{ display: 'none' }}
            onChange={async e => {
              const f = e.target.files?.[0]
              if (!f) return
              try { await api.flowShotImageUpload(flow.flow_id, shotIndex, f); say('参考图已上传', 'success'); onSaved() }
              catch (err: any) { say('上传失败: ' + err.message, 'error') }
              e.target.value = ''
            }} />
        </label>
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {refs.map((img: any, i: number) => (
          <div key={i} style={{ position: 'relative' }}>
            <img src={img.local_file ? `/dramas/${flow.drama_id}/images/${img.local_file}` : img.image_url}
              style={{ width: 52, height: 52, objectFit: 'cover', borderRadius: 4, border: '1px solid var(--border)' }} />
            {detail.custom_images.length > 0 && (
              <button onClick={async () => {
                await api.flowShotImageDelete(flow.flow_id, { shot_index: shotIndex, image_index: i })
                onSaved()
              }} style={{ position: 'absolute', top: -5, right: -5, width: 15, height: 15, borderRadius: '50%', background: 'var(--error)', color: '#fff', border: 'none', fontSize: 9, cursor: 'pointer', padding: 0, lineHeight: 1 }}>✕</button>
            )}
          </div>
        ))}
      </div>
      <div style={{ fontSize: 11, fontWeight: 600, margin: '8px 0 4px' }}>视频提示词（中文会自动翻译）</div>
      <textarea style={{ ...ta, minHeight: 80, fontSize: 12 }} value={prompt} onChange={e => setPrompt(e.target.value)} />
      <button style={{ ...btnSm, marginTop: 6 }} onClick={() => runShot(shotIndex, prompt ? { custom_prompt: prompt } : {})}>
        ▶ 用此提示词生成
      </button>
    </div>
  )
}

// ---------- 合并节点 ----------
export function MergeEditor({ flow, node, onSaved }: { flow: any, node: any, onSaved: () => void }) {
  void node
  const say = useToast().show
  const sh = flow.nodes ? Object.values<any>(flow.nodes).find((n: any) => n.type === 'shots' && n.output) : null
  const results: any[] = sh ? sh.output.results || [] : []
  const done = results.filter(r => r.status === 'completed' && r.local_file)
  const [order, setOrder] = useState<number[]>([])
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
      <div style={{ fontSize: 12, marginBottom: 8 }}>已完成的镜头：{done.map(d => `#${d.shot_index}`).join(', ') || '无'}</div>
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
        <button style={btn} disabled={order.length < 2} onClick={async () => {
          try {
            await api.flowMerge(flow.flow_id, { shot_indices: order, merge_name: name.trim() || `merge_${Date.now() % 10000}` })
            say('合并成功！', 'success')
            setOrder([])
            onSaved()
          } catch (e: any) { say('合并失败: ' + e.message, 'error') }
        }}>🧩 合并</button>
      </div>
      {mergedList.map((m: any, i: number) => (
        <div key={i} style={{ marginTop: 12, background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>🎬 {m.name}{m.shot_indices?.length ? `（${m.shot_indices.join(' → ')}）` : ''}</div>
          <video src={`/dramas/${flow.drama_id}/videos/${m.merged_file}`} controls style={{ width: '100%', maxWidth: 460, borderRadius: 6 }} />
          <a href={`/dramas/${flow.drama_id}/videos/${m.merged_file}`} download style={{ fontSize: 11, color: 'var(--accent)', display: 'inline-block', marginTop: 4 }}>⬇️ 下载</a>
        </div>
      ))}
    </div>
  )
}
