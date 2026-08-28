// 短剧节点流画布主页面
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ReactFlow, Background, Controls, MiniMap, addEdge,
  applyNodeChanges, applyEdgeChanges, MarkerType,
  type Connection, type Edge, type Node, type NodeChange, type EdgeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { api } from '../api/client'
import { useToast } from '../store/useToast'
import { useModels } from '../store/useModels'
import { FlowNodeCard } from '../components/flow/FlowNodeCard'
import { PromptEditor, TextEditor, StoryboardEditor, AssetsEditor, ShotsEditor, MergeEditor } from '../components/flow/NodeEditors'

const NODE_TYPES = { flowNode: FlowNodeCard }

// 节点顺序（连线校验 + 自动布局用）
const TYPE_ORDER: Record<string, number> = {
  prompt: 0, story: 1, script: 2, storyboard: 3, assets: 4, shots: 5, merge: 6,
}
const NODE_LABELS: Record<string, string> = {
  prompt: '✏️ 描述', story: '📖 故事', script: '📝 剧本', storyboard: '🎬 分镜',
  assets: '🖼 素材', shots: '🎥 镜头视频', merge: '🧩 合并',
}

function summarize(node: any, flow: any): { summary: string, thumbs: string[] } {
  const o = node.output
  if (!o) return { summary: '', thumbs: [] }
  switch (node.type) {
    case 'prompt': return { summary: String(o.prompt || ''), thumbs: [] }
    case 'story': case 'script': return { summary: String(o.text || '').slice(0, 80) + '…', thumbs: [] }
    case 'storyboard': return { summary: `共 ${(o.shots || []).length} 个镜头`, thumbs: [] }
    case 'assets': {
      const assets = o.assets || []
      return {
        summary: `${assets.filter((a: any) => a.image_url).length}/${assets.length} 个素材` + (o.progress ? `（${o.progress}）` : ''),
        thumbs: assets.filter((a: any) => a.local_file).map((a: any) => `/dramas/${flow.drama_id}/images/${a.local_file}`),
      }
    }
    case 'shots': {
      const rs = o.results || []
      const done = rs.filter((r: any) => r.status === 'completed')
      return {
        summary: `完成 ${done.length}/${rs.length}`,
        thumbs: done.slice(0, 2).map((r: any) => r.local_file ? `/dramas/${flow.drama_id}/videos/${r.local_file}` : '').filter(Boolean),
      }
    }
    case 'merge': return { summary: o.merged_file || '', thumbs: [] }
    default: return { summary: '', thumbs: [] }
  }
}

function toRfNodes(flow: any): Node[] {
  return Object.values(flow.nodes || {}).map((n: any) => {
    const { summary, thumbs } = summarize(n, flow)
    return {
      id: n.id, type: 'flowNode', position: n.pos || { x: 0, y: 0 },
      data: { nodeType: n.type, label: NODE_LABELS[n.type] || n.type, status: n.status, error: n.error || '', summary, thumbs },
    }
  })
}
function toRfEdges(flow: any): Edge[] {
  return (flow.edges || []).map((e: any) => ({
    id: e.id, source: e.source, target: e.target,
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
    style: { stroke: 'var(--accent)', strokeWidth: 1.5 },
  }))
}

const defaultLayout = (types: string[]) => {
  const nodes: Node[] = []
  const edges: Edge[] = []
  let prev = ''
  types.forEach((t, i) => {
    const id = `n${i + 1}`
    nodes.push({
      id, type: 'flowNode', position: { x: 60 + i * 280, y: TYPE_ORDER[t] === 4 || TYPE_ORDER[t] === 5 ? 320 : 80 },
      data: { nodeType: t, label: NODE_LABELS[t], status: 'pending', error: '', summary: '', thumbs: [] },
    })
    if (prev) edges.push({ id: `e${prev}-${id}`, source: prev, target: id, style: { stroke: 'var(--accent)', strokeWidth: 1.5 }, markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 } })
    prev = id
  })
  return { nodes, edges }
}

export function DramaFlowPage() {
  const toast = useToast()
  const models = useModels()
  // 启动参数
  const [prompt, setPrompt] = useState('')
  const [shotDuration, setShotDuration] = useState(5)
  const [textModel, setTextModel] = useState('agnes-2.5-flash')
  const [imageModel, setImageModel] = useState('agnes-image-2.1-flash')
  const [videoModel, setVideoModel] = useState('agnes-video-2.5-flash')
  const [charStyle, setCharStyle] = useState('anime')
  // 图状态
  const [nodes, setNodes] = useState<Node[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [flow, setFlow] = useState<any>(null)
  const [flowList, setFlowList] = useState<any[]>([])
  const [templates, setTemplates] = useState<any[]>([])
  const [selNodeId, setSelNodeId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (models?.defaults) {
      setTextModel(models.defaults.text_model)
      setImageModel(models.defaults.image_model)
      setVideoModel(models.defaults.video_model)
    }
  }, [models])

  const reloadList = useCallback(() => {
    api.flowList().then(d => setFlowList(d.flows || [])).catch(() => { })
    api.flowTemplates().then(d => setTemplates(d.templates || [])).catch(() => { })
  }, [])
  useEffect(() => { reloadList() }, [reloadList])

  // 打开流 + 轮询
  const openFlow = useCallback(async (fid: string) => {
    try {
      const d = await api.flowGet(fid)
      setFlow(d.flow)
      setNodes(toRfNodes(d.flow))
      setEdges(toRfEdges(d.flow))
      localStorage.setItem('currentFlowId', fid)
    } catch { localStorage.removeItem('currentFlowId') }
  }, [])
  useEffect(() => {
    const saved = localStorage.getItem('currentFlowId')
    if (saved) openFlow(saved)
    else { const l = defaultLayout(['prompt', 'story', 'script', 'storyboard', 'assets', 'shots', 'merge']); setNodes(l.nodes); setEdges(l.edges) }
  }, [openFlow])

  useEffect(() => {
    if (!flow) return
    const busy = Object.values(flow.nodes || {}).some((n: any) => n.status === 'running') ||
      Object.values(flow.nodes || {}).some((n: any) => n.type === 'shots' && (n.output?.results || []).some((r: any) => r.status === 'generating'))
    if (!busy) { if (pollRef.current) clearInterval(pollRef.current); return }
    pollRef.current = setInterval(() => {
      api.flowGet(flow.flow_id).then(d => {
        setFlow(d.flow)
        setNodes(ns => ns.map(n => {
          const fn = d.flow.nodes[n.id]
          if (!fn) return n
          const { summary, thumbs } = summarize(fn, d.flow)
          return { ...n, data: { ...n.data, status: fn.status, error: fn.error || '', summary, thumbs } }
        }))
      }).catch(() => { })
    }, 5000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [flow?.flow_id, flow?.nodes && JSON.stringify(Object.values(flow.nodes).map((n: any) => n.status))])

  const onNodesChange = useCallback((ch: NodeChange[]) => setNodes(ns => applyNodeChanges(ch, ns)), [])
  const onEdgesChange = useCallback((ch: EdgeChange[]) => setEdges(es => applyEdgeChanges(ch, es)), [])
  const onConnect = useCallback((c: Connection) => {
    const src = nodes.find(n => n.id === c.source)?.data as any
    const tgt = nodes.find(n => n.id === c.target)?.data as any
    if (!src || !tgt) return
    if ((TYPE_ORDER[src.nodeType] ?? 9) >= (TYPE_ORDER[tgt.nodeType] ?? 9)) {
      toast.show('连线必须从上游指向下游（描述→…→合并）', 'error')
      return
    }
    if (c.source === c.target) return
    setEdges(es => addEdge({ ...c, markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 }, style: { stroke: 'var(--accent)', strokeWidth: 1.5 } }, es))
  }, [nodes, toast])

  // 同步图到后端（位置/连线/删除）
  const syncGraph = useCallback(async () => {
    if (!flow) return
    try {
      await api.flowSaveGraph(flow.flow_id, {
        nodes: nodes.map(n => ({ id: n.id, type: (n.data as any).nodeType, pos: n.position })),
        edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target })),
      })
    } catch { }
  }, [flow, nodes, edges])
  const debRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const scheduleSync = useCallback(() => {
    if (debRef.current) clearTimeout(debRef.current)
    debRef.current = setTimeout(syncGraph, 1200)
  }, [syncGraph])
  useEffect(() => { scheduleSync() }, [nodes, edges, scheduleSync])

  // ---------- 操作 ----------
  const createFlow = async () => {
    if (!prompt.trim()) { toast.show('请输入短剧描述', 'error'); return }
    try {
      const d = await api.flowCreate({
        prompt, shot_duration: shotDuration, text_model: textModel,
        image_model: imageModel, video_model: videoModel, character_style: charStyle,
      })
      toast.show('已创建节点流', 'success')
      reloadList()
      openFlow(d.flow_id)
    } catch (e: any) { toast.show('创建失败: ' + e.message, 'error') }
  }

  const runAll = async () => {
    try {
      await api.flowRun(flow.flow_id)
      toast.show('开始运行未完成的节点', 'info')
      setTimeout(() => openFlow(flow.flow_id), 800)
    } catch (e: any) { toast.show(e.message, 'error') }
  }
  const runNode = async (nodeId: string) => {
    try { await api.flowRun(flow.flow_id, { node_id: nodeId, force: true }); setTimeout(() => openFlow(flow.flow_id), 800) }
    catch (e: any) { toast.show(e.message, 'error') }
  }
  const runDownstream = async (nodeId: string) => {
    try { await api.flowRunDownstream(flow.flow_id, nodeId); setTimeout(() => openFlow(flow.flow_id), 800) }
    catch (e: any) { toast.show(e.message, 'error') }
  }
  const stopFlow = async () => { await api.flowStop(flow.flow_id); toast.show('已发送停止信号', 'info') }

  const saveTemplate = async () => {
    const name = prompt.trim() || flow?.name || `模板_${Date.now() % 10000}`
    try { await api.flowTemplateSave(flow.flow_id, name); toast.show('模板已保存: ' + name, 'success'); reloadList() }
    catch (e: any) { toast.show(e.message, 'error') }
  }
  const newFromTemplate = async (name: string) => {
    try {
      const d = await api.flowCreate({ prompt, template: name })
      toast.show('已从模板创建', 'success')
      reloadList()
      openFlow(d.flow_id)
    } catch (e: any) { toast.show(e.message, 'error') }
  }
  const resetFlow = async () => {
    if (!confirm('清空所有节点结果并回到待运行状态？')) return
    await api.flowReset(flow.flow_id)
    openFlow(flow.flow_id)
  }
  const deleteFlow = async () => {
    if (!confirm('删除该节点流？')) return
    await api.flowDelete(flow.flow_id)
    localStorage.removeItem('currentFlowId')
    setFlow(null)
    reloadList()
  }
  const addNode = (t: string) => {
    const id = `n${Date.now() % 100000}`
    setNodes(ns => [...ns, {
      id, type: 'flowNode', position: { x: 120 + Math.random() * 200, y: 80 + Math.random() * 200 },
      data: { nodeType: t, label: NODE_LABELS[t], status: 'pending', error: '', summary: '', thumbs: [] },
    }])
    toast.show('已添加节点，自动保存到后端', 'info')
  }
  const onNodeClick = useCallback((_: any, n: Node) => { setSelNodeId(n.id); setDrawerOpen(true) }, [])

  const selNode = useMemo(() => selNodeId && flow ? (flow.nodes?.[selNodeId] || null) : null, [selNodeId, flow])

  const sel = { padding: '6px 10px', fontSize: 12 }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      {/* 顶部工具栏 */}
      <div className="card" style={{ padding: 12 }}>
        <div className="card-header" style={{ marginBottom: 8 }}>🕸 短剧节点流（拖拽画布）</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
          <input className="form-input" placeholder="输入短剧描述，点击右侧新建流…" value={prompt} onChange={e => setPrompt(e.target.value)} style={{ flex: 2, minWidth: 220, ...sel }} />
          <select className="form-select" value={shotDuration} onChange={e => setShotDuration(Number(e.target.value))} style={{ width: 110, ...sel }}>
            <option value={5}>5 秒/镜</option><option value={10}>10 秒/镜</option><option value={18}>18 秒/镜</option>
          </select>
          <select className="form-select" value={textModel} onChange={e => setTextModel(e.target.value)} style={{ width: 160, ...sel }}>
            {models && Object.entries(models.text_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
          <select className="form-select" value={imageModel} onChange={e => setImageModel(e.target.value)} style={{ width: 160, ...sel }}>
            {models && Object.entries(models.image_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
          <select className="form-select" value={videoModel} onChange={e => setVideoModel(e.target.value)} style={{ width: 160, ...sel }}>
            {models && Object.entries(models.video_models).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}
          </select>
          <select className="form-select" value={charStyle} onChange={e => setCharStyle(e.target.value)} style={{ width: 120, ...sel }}>
            <option value="anime">动漫卡通</option><option value="realistic">写实真人</option>
            <option value="pixar3d">皮克斯3D</option><option value="semi_realistic">半写实插画</option>
            <option value="watercolor">水彩手绘</option><option value="ink">中国水墨</option>
          </select>
          <button className="btn btn-primary" onClick={createFlow}>＋ 新建流</button>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <select className="form-select" style={{ width: 260, ...sel }} value={flow?.flow_id || ''} onChange={e => e.target.value && openFlow(e.target.value)}>
            <option value="">— 选择已有流 —</option>
            {flowList.map(f => <option key={f.flow_id} value={f.flow_id}>{f.name}（{f.done}/{f.total}）</option>)}
          </select>
          {flow && <>
            <button className="btn btn-primary" style={{ padding: '6px 14px', fontSize: 12 }} onClick={runAll}>▶ 运行未完成节点</button>
            <button className="btn" style={sel} onClick={stopFlow}>⏹ 停止</button>
            <button className="btn" style={sel} onClick={resetFlow}>♻ 重置结果</button>
            <button className="btn" style={sel} onClick={saveTemplate}>💾 存为模板</button>
            <button className="btn" style={{ ...sel, color: 'var(--error)' }} onClick={deleteFlow}>🗑 删除流</button>
            <span style={{ fontSize: 11, color: 'var(--text2)' }}>flow {flow.flow_id}</span>
          </>}
          <select className="form-select" style={{ width: 200, ...sel }} value="" onChange={e => e.target.value && newFromTemplate(e.target.value)}>
            <option value="">— 从模板创建 —</option>
            {templates.map(t => <option key={t.name} value={t.name}>{t.name}（{t.nodes} 节点）</option>)}
          </select>
          <span style={{ fontSize: 11, color: 'var(--text2)' }}>
            ＋节点:
          </span>
          {['story', 'script', 'storyboard', 'assets', 'shots', 'merge'].map(t => (
            <button key={t} style={{ ...sel, border: '1px solid var(--border)', background: 'var(--bg)', borderRadius: 5, cursor: 'pointer', color: 'var(--text)' }} onClick={() => addNode(t)}>{NODE_LABELS[t]}</button>
          ))}
        </div>
      </div>

      {/* 画布 + 抽屉 */}
      <div style={{ flex: 1, display: 'flex', gap: 12, minHeight: 480 }}>
        <div style={{ flex: 1, background: 'var(--surface)', borderRadius: 'var(--radius)', border: '1px solid var(--border)', position: 'relative', minWidth: 0 }}>
          <ReactFlow
            nodes={nodes} edges={edges}
            onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
            onNodeClick={onNodeClick}
            nodeTypes={NODE_TYPES}
            fitView deleteKeyCode={['Backspace', 'Delete']}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={16} size={1} color="var(--border)" />
            <Controls />
            <MiniMap pannable zoomable style={{ background: 'var(--bg)' }} />
          </ReactFlow>
          {!flow && <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text2)', fontSize: 14, pointerEvents: 'none' }}>
            输入描述后点「＋ 新建流」，或从左侧选择已有流
          </div>}
        </div>

        {drawerOpen && selNode && flow && (
          <div style={{ width: 460, flexShrink: 0, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 12, overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
              <b>{NODE_LABELS[selNode.type] || selNode.type} · 节点详情</b>
              <div style={{ display: 'flex', gap: 6 }}>
                <button style={{ ...sel, border: '1px solid var(--border)', background: 'var(--bg)', borderRadius: 4, cursor: 'pointer', color: 'var(--text)' }} onClick={() => runNode(selNode.id)}>▶ 运行此节点</button>
                <button style={{ ...sel, border: '1px solid var(--border)', background: 'var(--bg)', borderRadius: 4, cursor: 'pointer', color: 'var(--text)' }} onClick={() => runDownstream(selNode.id)}>▶ 运行下游</button>
                <button style={{ ...sel, border: 'none', background: 'none', cursor: 'pointer', color: 'var(--text2)' }} onClick={() => setDrawerOpen(false)}>✕</button>
              </div>
            </div>
            {selNode.type === 'prompt' ?
              <PromptEditor key={selNode.id} flow={flow} onSaved={() => openFlow(flow.flow_id)} />
              : selNode.type === 'story' || selNode.type === 'script' ?
              <TextEditor key={selNode.id + selNode.updated_at} flow={flow} node={selNode} onSaved={() => openFlow(flow.flow_id)} />
              : selNode.type === 'storyboard' ?
                <StoryboardEditor key={selNode.id + selNode.updated_at} flow={flow} node={selNode} onSaved={() => openFlow(flow.flow_id)} />
                : selNode.type === 'assets' ?
                  <AssetsEditor key={selNode.id + (selNode.output?.assets?.length || 0)} flow={flow} node={selNode} onSaved={() => openFlow(flow.flow_id)} />
                  : selNode.type === 'shots' ?
                    <ShotsEditor key={selNode.id + (selNode.output?.results?.length || 0)} flow={flow} node={selNode} onSaved={() => openFlow(flow.flow_id)} />
                    : selNode.type === 'merge' ?
                      <MergeEditor key={selNode.id} flow={flow} node={selNode} onSaved={() => openFlow(flow.flow_id)} />
                      : <div style={{ fontSize: 12, color: 'var(--text2)' }}>在顶部工具栏修改描述后运行即可</div>}
          </div>
        )}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text2)' }}>
        操作：拖动节点摆位 · 右侧圆点拉线连接 · 选中节点按 Delete 移除 · 点节点开右侧编辑面板 · 运行只跑未完成/需重跑的节点
      </div>
    </div>
  )
}
