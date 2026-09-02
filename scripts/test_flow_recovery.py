"""镜头 override 落盘 / inflight 回收 / 已完成镜头复用 的最小自检。运行: python scripts/test_flow_recovery.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.routes import drama_flow as df

_tmp = tempfile.mkdtemp()
df.get_app_dir = lambda: _tmp  # 读写落盘全部重定向临时目录


def test_override_roundtrip():
    fid = 'test1'
    with df.flow_lock:
        df.flows[fid] = {'flow_id': fid, 'drama_id': fid, 'params': {}, 'name': 'x',
                         'nodes': {}, 'edges': [], 'created_at': 0,
                         'shot_overrides': {'3': {'custom_prompt': 'cat', 'custom_images': [{'image_url': '/a.png'}]}}}
    df._persist(fid)
    with df.flow_lock:
        df.flows.pop(fid)
    loaded = df._load_flow(fid)
    ov = loaded['shot_overrides']['3']
    assert ov['custom_prompt'] == 'cat' and ov['custom_images'][0]['image_url'] == '/a.png'


def test_generating_mark_and_inflight_kept():
    fid = 'test2'
    with df.flow_lock:
        df.flows[fid] = {'flow_id': fid, 'drama_id': fid, 'params': {}, 'name': 'x', 'edges': [], 'created_at': 0,
                         'inflight': {'1': {'shot_index': 1, 'task_id': 't'}},
                         'nodes': {'n1': {'id': 'n1', 'type': 'shots', 'status': 'completed', 'output': {'results': [
                             {'shot_index': 0, 'status': 'generating'},
                             {'shot_index': 1, 'status': 'generating'}]}}}}
    df._persist(fid)
    with df.flow_lock:
        df.flows.pop(fid)
    loaded = df._load_flow(fid)
    rs = {r['shot_index']: r for r in loaded['nodes']['n1']['output']['results']}
    assert rs[0]['status'] == 'failed' and '重启' in rs[0]['error']
    assert rs[1]['status'] == 'generating'  # 有在途任务，留给回收线程
    assert loaded['inflight']['1']['task_id'] == 't'


def test_reuse_only_existing_files():
    drama = 'test3'
    vdir = os.path.join(_tmp, 'dramas', drama, 'videos')
    os.makedirs(vdir, exist_ok=True)
    open(os.path.join(vdir, 'a.mp4'), 'w').close()
    node = {'id': 'n', 'type': 'shots', 'output': {'results': [
        {'shot_index': 0, 'status': 'completed', 'local_file': 'a.mp4'},
        {'shot_index': 1, 'status': 'completed', 'local_file': 'missing.mp4'},
        {'shot_index': 2, 'status': 'failed'}]}}
    reused = df._reuse_completed_shots({'flow_id': 'f', 'drama_id': drama, 'params': {}}, node,
                                       [{'shot_index': 0}, {'shot_index': 1}, {'shot_index': 2}], drama)
    assert set(reused) == {0}


def test_shot_reuse_fingerprint():
    drama = 'test6'
    vdir = os.path.join(_tmp, 'dramas', drama, 'videos')
    os.makedirs(vdir, exist_ok=True)
    open(os.path.join(vdir, 'a.mp4'), 'w').close()
    params = {'shot_duration': 5}
    flow = {'flow_id': 'f', 'drama_id': drama, 'params': params, '_shot_assets_cache': []}
    shot = {'shot_index': 0, 'dialogue': '你好'}
    node = {'id': 'n', 'type': 'shots', 'output': {'results': [
        {'shot_index': 0, 'status': 'completed', 'local_file': 'a.mp4'}]}}
    assert 0 in df._reuse_completed_shots(flow, node, [shot], drama)      # 旧数据无 fp → 信任
    node['output']['results'][0]['fp'] = df._shot_fp(shot, params, '')
    assert 0 in df._reuse_completed_shots(flow, node, [shot], drama)      # 指纹一致 → 复用
    changed = dict(shot, dialogue='一' * 40)                              # 分镜台词变多 → 时长升档
    assert 0 not in df._reuse_completed_shots(flow, node, [changed], drama)
    flow_long = dict(flow, params={'shot_duration': 18})                  # 时长档位变化
    assert 0 not in df._reuse_completed_shots(flow_long, node, [shot], drama)
    # 首参考图变化（自动匹配 → 自定义）→ 指纹不同 → 不可复用
    fp_auto = df._shot_fp(shot, params, df._match_assets(shot, [])[1])
    fp_custom = df._shot_fp(shot, params, '/own.png')
    assert fp_auto != fp_custom
    ov_flow = {'flow_id': 'f', 'drama_id': drama, 'params': params, '_shot_assets_cache': [],
               'shot_overrides': {'0': {'custom_images': [{'image_url': '/own.png'}]}}}
    assert 0 not in df._reuse_completed_shots(ov_flow, node, [shot], drama)


def test_prompt_edit_invalidates_chain():
    fid = 'test7'
    flow = {'flow_id': fid, 'drama_id': fid, 'params': {'prompt': 'old'}, 'name': 'x', 'created_at': 0,
            'edges': [{'source': 'a', 'target': 'b'}],
            'nodes': {'a': {'id': 'a', 'type': 'prompt', 'status': 'completed', 'output': {'prompt': 'old'}},
                      'b': {'id': 'b', 'type': 'story', 'status': 'completed', 'output': {'text': 'x'}}}}
    flow['nodes']['a']['sig'] = df._node_sig(flow, 'a')
    flow['nodes']['b']['sig'] = df._node_sig(flow, 'b')
    assert df._cache_hit(flow, 'a') and df._cache_hit(flow, 'b')   # 改描述前：全签名命中（=静默空跑的根源）
    flow['params']['prompt'] = 'new'                               # 签名不含全局 prompt：仍命中 → 需显式失效
    assert df._cache_hit(flow, 'a')
    with df.flow_lock:
        df.flows[fid] = flow
    df._invalidate_prompt_nodes(fid)
    assert flow['nodes']['a']['status'] == 'stale' and flow['nodes']['b']['status'] == 'stale'
    assert df._upstream_pending(flow, 'b') == ['a', 'b']           # 直接跑下游也会先补齐 prompt


def test_recover_finish_writes_back_and_persists():
    fid = 'test4'
    entry = {'shot_index': 2, 'task_id': 'x', 'save_subdir': 'dramas/test4/videos', 'prompt': 'p'}
    with df.flow_lock:
        df.flows[fid] = {'flow_id': fid, 'drama_id': fid, 'params': {}, 'name': 'x', 'edges': [], 'created_at': 0,
                         'inflight': {'2': entry},
                         'nodes': {'n1': {'id': 'n1', 'type': 'shots', 'status': 'pending', 'output': {'results': [
                             {'shot_index': 2, 'status': 'generating'}]}}}}
    df._recover_finish(fid, entry, df._recovered_result(entry, error='云端任务不存在或已过期'))
    result = df.flows[fid]['nodes']['n1']['output']['results']
    assert len(result) == 1 and result[0]['status'] == 'failed' and result[0]['recovered'] is True
    assert df.flows[fid]['inflight'] == {}
    with df.flow_lock:
        df.flows.pop(fid)
    loaded = df._load_flow(fid)
    assert loaded['inflight'] == {} and loaded['nodes']['n1']['output']['results'][0]['status'] == 'failed'


def test_upstream_pending_skips_completed():
    flow = {'params': {}, 'nodes': {'n1': {'id': 'n1', 'type': 'prompt', 'status': 'completed'},
                                    'n2': {'id': 'n2', 'type': 'story', 'status': 'pending'},
                                    'n3': {'id': 'n3', 'type': 'script', 'status': 'stale'}},
            'edges': [{'source': 'n1', 'target': 'n2'}, {'source': 'n2', 'target': 'n3'}]}
    assert df._upstream_pending(flow, 'n3') == ['n2', 'n3']
    assert df._upstream_pending(flow, 'n1') == ['n1']


def test_sig_cache_hit_and_invalidate():
    flow = {'flow_id': 't5', 'drama_id': 't5', 'params': {}, 'created_at': 0,
            'edges': [{'source': 'n1', 'target': 'n2'}],
            'nodes': {'n1': {'id': 'n1', 'type': 'prompt', 'status': 'completed', 'output': {'prompt': 'cat'}},
                      'n2': {'id': 'n2', 'type': 'story', 'status': 'completed', 'output': {'text': 'x'}}}}
    flow['nodes']['n1']['sig'] = df._node_sig(flow, 'n1')
    flow['nodes']['n2']['sig'] = df._node_sig(flow, 'n2')
    assert df._cache_hit(flow, 'n2') is True
    flow['nodes']['n1']['output'] = {'prompt': 'dog'}          # 上游重跑且输出变了 → 失效
    assert df._cache_hit(flow, 'n2') is False
    flow['nodes']['n1']['output'] = {'prompt': 'cat'}          # 上游重跑但输出没变 → 命中（省钱核心）
    assert df._cache_hit(flow, 'n2') is True
    flow['nodes']['n2']['params'] = {'text_model': 'other'}    # 节点级参数覆盖 → 失效
    assert df._cache_hit(flow, 'n2') is False
    del flow['nodes']['n2']['params']
    assert df._cache_hit(flow, 'n2') is True


def test_duration_engine():
    long_shot = {'shot_index': 1, 'dialogue': '一' * 40}   # 40字/4.5≈8.9s + 2.5 = 11.4s → 升 10 秒档
    assert df._fit_shot_duration(long_shot, 5) == 10
    assert df._fit_shot_duration({'shot_index': 2, 'dialogue': '你好'}, 5) == 5
    warnings, over = df._validate_shots([{'shot_index': 1, 'dialogue': '一' * 200}], 5)
    assert over and '超过最长' in over[0]
    warnings, over = df._validate_shots([{'shot_index': 1, 'dialogue': '一' * 40}], 5)
    assert not over and warnings and '10 秒档' in warnings[0]


def test_crosscheck_refs():
    w = df._crosscheck_refs([{'shot_index': 1, 'characters': ['九叔', '神秘路人']}], [{'name': '九叔'}])
    assert w == [{'shot_index': 1, 'kind': '角色', 'name': '神秘路人'}]


def test_review_shots_fallback():
    orig = df.call_text_model
    shots = [{'shot_index': 1, 'dialogue': 'x'}]
    try:
        df.call_text_model = lambda *a, **k: '完全不是JSON'
        assert df._review_shots(shots, 'k', 'm', 'noflow') == shots          # 解析失败 → 原稿
        df.call_text_model = lambda *a, **k: '{"shots": [{"shot_index": 1}, {"shot_index": 2}]}'
        assert len(df._review_shots(shots, 'k', 'm', 'noflow')) == 2          # 正常修订 → 采用
        df.call_text_model = lambda *a, **k: '{"shots": [' + ','.join('{"shot_index":%d}' % i for i in range(1, 20)) + ']}'
        assert df._review_shots(shots, 'k', 'm', 'noflow') == shots           # 偏差过大 → 原稿
    finally:
        df.call_text_model = orig


def test_abort_check():
    import src.services.text_model as tm
    import requests as rq
    flag = {'aborted': False}
    orig_post = rq.post
    try:
        def fake_post(*a, **k):
            flag['aborted'] = True
            class R: status_code = 429; text = 'rate'; headers = {}
            return R()
        rq.post = fake_post
        try:
            tm.call_text_model('s', 'u', 'k', abort_check=lambda: flag['aborted'])
            assert False, '应抛出已中止'
        except RuntimeError as e:
            assert '已中止' in str(e)
    finally:
        rq.post = orig_post


def test_sanitize_word_boundary():
    from src.services.text_model import sanitize_image_prompt
    assert sanitize_image_prompt('blood-red glowing eyes, warm light') == 'red glowing eyes, warm light'
    assert 'killer' in sanitize_image_prompt('a killer whale')          # 不再被打成 'er whale'
    assert sanitize_image_prompt('暴力场面') == '场面'                    # 中文直接替换
    assert 'Scene: dead' not in sanitize_image_prompt('x')               # smoke 无异常


def test_video_prompt_scene_first():
    from src.services.text_model import build_video_prompt
    en, cn = build_video_prompt({'prompt_en': 'A zombie rises from the altar', 'scene_desc': '僵尸起身',
                                 'camera': '全景 固定'}, [])
    assert en.startswith('A zombie rises'), en[:80]
    assert 'No text, no subtitles' in en


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print(f'ok {name}')
    print('ALL PASS')
