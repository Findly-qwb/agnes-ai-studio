"""
API 配置路由
"""

import os
import json
from flask import Blueprint, request, jsonify
from ..config import get_config_path

config_bp = Blueprint('config', __name__)


@config_bp.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """获取/保存 API Key 配置（支持各厂商独立 Key）"""
    config_file = get_config_path()
    
    def _mask_key(key):
        if not key:
            return ''
        return key[:8] + '****' + key[-4:] if len(key) > 12 else '****'
    
    if request.method == 'GET':
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            result = {}
            for k, v in data.items():
                if k.endswith('_api_key') or k == 'api_key':
                    result[k] = ''
                    result[f'{k}_masked'] = _mask_key(v) if v else ''
                elif k.endswith('_base_url'):
                    result[k] = v
                else:
                    result[k] = v
            return jsonify(result)
        return jsonify({'api_key': '', 'api_key_masked': ''})

    elif request.method == 'POST':
        data = request.get_json()
        config = {}
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        
        api_key = data.get('api_key', '').strip()
        if api_key:
            config['api_key'] = api_key
        
        vendor_keys = ['text_api_key', 'deepseek_api_key', 'doubao_api_key', 'minimax_api_key', 'qwen_api_key']
        vendor_urls = ['text_base_url', 'deepseek_base_url', 'doubao_base_url', 'minimax_base_url', 'qwen_base_url']
        
        for key_field in vendor_keys:
            val = data.get(key_field, '').strip()
            if val:
                config[key_field] = val
            elif key_field in data:
                config.pop(key_field, None)
        
        for url_field in vendor_urls:
            val = data.get(url_field, '').strip()
            if val:
                config[url_field] = val
            elif url_field in data:
                config.pop(url_field, None)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        return jsonify({'success': True, 'message': '配置已保存'})
