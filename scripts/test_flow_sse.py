"""SSE 事件流最小自检：连接立即首帧快照、_persist/_bump 后推变更帧。运行: python scripts/test_flow_sse.py"""
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.routes import drama_flow as df

_tmp = tempfile.mkdtemp()
df.get_app_dir = lambda: _tmp  # 落盘重定向临时目录


def test_sse_initial_frame_and_change_push():
    from src import create_app
    app = create_app()
    with app.test_client() as c:
        fid = c.post('/api/drama/flow/create', json={'prompt': '测试'}).get_json()['flow_id']
    with app.app_context():
        resp = df.flow_events(fid)
        it = iter(resp.response)  # 原始 generator，绕过 Response 包装
        p1 = next(it)
        frame = json.loads(p1.removeprefix('data: ').strip())
        assert frame['flow_id'] == fid
        assert '_shot_assets_cache' not in frame and all(not k.startswith('_') for k in frame)

        df._persist(fid)                      # 落盘 → bump → 应推第二帧
        p2 = next(it)
        assert p2.startswith('data:') and json.loads(p2.removeprefix('data: '))['flow_id'] == fid

        df._bump(fid)                         # 不写盘的内存变化也要能推
        p3 = next(it)
        assert p3.startswith('data:')
    print('ok sse frames: initial + persist + bump')


def test_sse_404_for_missing_flow():
    from src import create_app
    app = create_app()
    with app.app_context():
        resp, code = df.flow_events('nonexistent')
        assert code == 404
    print('ok sse 404')


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
    print('ALL PASS')
