"""
视频拼接模块 (ffmpeg)
包含：ffmpeg 路径查找、视频合并
"""

import os
import subprocess
from datetime import datetime
from ..config import get_app_dir


def get_ffmpeg_path():
    """获取 ffmpeg 可执行文件路径（优先系统 PATH，其次 imageio-ffmpeg 内置）"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return 'ffmpeg'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_exe and os.path.exists(ffmpeg_exe):
            return ffmpeg_exe
    except ImportError:
        pass
    return None


def merge_videos(drama_id, video_results):
    """使用 ffmpeg 将多个分镜视频拼接为一个完整视频
    
    Args:
        drama_id: 短剧 ID
        video_results: 视频结果列表（包含 local_file 字段）
    
    Returns:
        合并后的文件名，失败返回 None
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        print(f"[短剧 {drama_id}] 警告: 未找到 ffmpeg，跳过视频拼接")
        return None
    
    success_videos = []
    for v in sorted(video_results, key=lambda x: x.get('shot_index', 0)):
        if v.get('status') == 'completed' and v.get('local_file'):
            app_dir = get_app_dir()
            full_path = os.path.join(app_dir, 'dramas', drama_id, 'videos', v['local_file'])
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                success_videos.append(full_path)
    
    if len(success_videos) < 2:
        print(f"[短剧 {drama_id}] 成功视频少于 2 个，跳过拼接")
        return None
    
    print(f"[短剧 {drama_id}] 开始拼接 {len(success_videos)} 个视频...")
    
    app_dir = get_app_dir()
    videos_dir = os.path.join(app_dir, 'dramas', drama_id, 'videos')
    list_file = os.path.join(videos_dir, 'concat_list.txt')
    
    try:
        with open(list_file, 'w', encoding='utf-8') as f:
            for video_path in success_videos:
                safe_path = video_path.replace('\\', '/')
                f.write(f"file '{safe_path}'\n")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'merged_{timestamp}.mp4'
        output_path = os.path.join(videos_dir, output_file)
        
        cmd = [
            ffmpeg, '-f', 'concat', '-safe', '0',
            '-i', list_file, '-c', 'copy', '-y', output_path
        ]
        
        print(f"[短剧 {drama_id}] 执行: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size = os.path.getsize(output_path) // 1024
            print(f"[短剧 {drama_id}] 拼接成功: {output_file} ({file_size}KB)")
            return output_file
        else:
            print(f"[短剧 {drama_id}] 拼接失败: {result.stderr[:500]}")
            print(f"[短剧 {drama_id}] 尝试重新编码模式...")
            cmd_reencode = [
                ffmpeg, '-f', 'concat', '-safe', '0',
                '-i', list_file, '-c:v', 'libx264', '-c:a', 'aac', '-y', output_path
            ]
            result2 = subprocess.run(cmd_reencode, capture_output=True, text=True, timeout=600)
            if result2.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size = os.path.getsize(output_path) // 1024
                print(f"[短剧 {drama_id}] 重新编码拼接成功: {output_file} ({file_size}KB)")
                return output_file
            else:
                print(f"[短剧 {drama_id}] 重新编码也失败: {result2.stderr[:500]}")
                return None
    except subprocess.TimeoutExpired:
        print(f"[短剧 {drama_id}] 拼接超时")
        return None
    except Exception as e:
        print(f"[短剧 {drama_id}] 拼接异常: {e}")
        return None
    finally:
        if os.path.exists(list_file):
            try:
                os.remove(list_file)
            except:
                pass
