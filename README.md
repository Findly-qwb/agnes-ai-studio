# Agnes AI Studio

一个基于 Agnes AI API 的图片和视频生成可视化工具，提供美观的 Web 操作界面。

## 功能

- **🖼 文生图** - 通过文本描述生成高质量图片
- **🎨 图生图** - 基于参考图片进行风格转换和编辑
- **🎬 文生视频** - 通过文本描述生成视频
- **🖼→🎬 图生视频** - 让静态图片动起来
- **📋 短剧生成** - 一键生成完整短剧（剧本→分镜→素材→视频→拼接）
- **📋 任务管理** - 实时查看视频生成任务状态和进度
- **⚙ API Key 管理** - 可视化配置和管理多厂商 API Key
- **🔀 多厂商支持** - 自动路由至 Agnes AI / DeepSeek 等厂商 API

---

## 🚀 方式一：使用打包好的 EXE（推荐，无需安装任何环境）

适合**没有 Python 环境**的用户，直接双击运行。

### 使用步骤

1. 将 `dist/Agnes-AI-Studio.exe` 复制到任意目录
2. **双击运行** `Agnes-AI-Studio.exe`
3. 浏览器会自动打开 `http://127.0.0.1:5000`
4. 点击右上角「⚙ 设置」，输入 API Key 即可使用

> 💡 **分享给他人**：只需发送这一个 `Agnes-AI-Studio.exe` 文件（约 46MB）即可！

### 如何打包

```bash
# 安装 PyInstaller
pip install pyinstaller

# 执行打包脚本
build.bat
# 或者手动执行：
pyinstaller --clean --noconfirm Agnes-AI-Studio.spec
```

输出文件在 `dist/Agnes-AI-Studio.exe`。

---

## 🐍 方式二：源码运行（适合开发者）

### 1. 获取 API Key

访问 [Agnes AI 平台](https://platform.agnes-ai.cn) 注册账号并获取免费 API Key。

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动服务

**Windows:**
```bash
start.bat
```

**Mac/Linux:**
```bash
chmod +x start.sh
./start.sh
```

### 4. 打开浏览器

访问 `http://127.0.0.1:5000`

### 5. 配置 API Key

点击右上角「⚙ 设置」按钮，输入你的 API Key 并保存。

---

## API 说明

### 文本模型（用于短剧剧本/分镜/素材生成）

| 模型 | 用途 |
|------|------|
| `deepseek-v4-flash` | 剧本生成、分镜改写、素材提取（推荐） |
| `deepseek-v3` | 高质量文本生成 |
| `agnes-text-v2` | Agnes AI 平台文本模型 |

### 图片生成模型

| 模型 | 用途 |
|------|------|
| `agnes-image-2.1-flash` | 文生图 / 素材参考图生成（推荐） |
| `agnes-image-2.0-flash` | 图生图 / 图片编辑 |

### 视频生成模型

| 模型 | 用途 |
|------|------|
| `agnes-video-v2.0` | 文生视频 / 图生视频 / 短剧镜头生成 |

### 视频参数说明

- **num_frames**: 帧数，需满足 8n+1 格式，最大 ≤441
- **frame_rate**: 帧率，范围 1-60
- **时长公式**: seconds = num_frames / frame_rate
- 推荐配置: 121帧/24fps ≈ 5秒, 241帧/24fps ≈ 10秒

## 项目结构

```
agnes-ai-studio/
├── app.py                  # 入口文件（精简，约 45 行）
├── config.json             # API Key 配置（不纳入 Git）
├── requirements.txt        # Python 依赖
├── start.bat / start.sh    # 启动脚本
├── build.bat               # 打包脚本
├── Agnes-AI-Studio.spec    # PyInstaller 配置
├── version_info.txt        # EXE 版本信息
├── static/
│   └── index.html          # 前端 Web 界面
├── src/                    # 核心源码（模块化）
│   ├── __init__.py         # 应用工厂（create_app + 注册 Blueprint）
│   ├── config.py           # 路径工具、API Key 读写、厂商路由
│   ├── models.py           # 模型选项、任务状态、共享数据
│   ├── services/           # 业务逻辑层
│   │   ├── text_model.py   # 文本模型调用 + Prompt 模板
│   │   ├── video_gen.py    # 视频生成 / 轮询 / 下载
│   │   └── video_merge.py  # ffmpeg 视频拼接
│   └── routes/             # 路由层（Flask Blueprint）
│       ├── pages.py        # 首页 + 静态文件服务
│       ├── api_config.py   # API 配置读写
│       ├── image.py        # 图片生成 + 上传
│       ├── video.py        # 视频生成 + 状态查询
│       ├── drama.py        # 短剧流水线（剧本→分镜→素材→视频→拼接）
│       └── files.py        # 文件列表 + 关闭服务
└── dist/
    └── Agnes-AI-Studio.exe # 打包后的独立可执行文件
```

### 模块说明

| 模块 | 职责 |
|------|------|
| `src/config.py` | 路径工具（兼容 PyInstaller）、API Key 读写、厂商 Base URL 路由 |
| `src/models.py` | 文本/图片/视频模型选项、视频任务状态、短剧任务状态 |
| `src/services/text_model.py` | OpenAI 兼容接口调用、JSON 解析、剧本/分镜/素材 Prompt 模板 |
| `src/services/video_gen.py` | 文件下载（支持重试）、视频状态轮询（含 content 端点 fallback） |
| `src/services/video_merge.py` | ffmpeg 路径查找、多段视频拼接 |
| `src/routes/drama.py` | 短剧 5 步流水线（后台线程）、短剧 API 路由 |

## 技术栈

- **后端**: Python Flask + Flask-CORS + Requests
- **前端**: 原生 HTML/CSS/JS (无需额外框架)
- **架构**: Flask Blueprint 模块化 + 应用工厂模式
- **打包**: PyInstaller (单文件 EXE)
- **API**: Agnes AI / DeepSeek (OpenAI 兼容协议)

## API Key 配置说明

支持多厂商 API Key 独立配置，系统根据模型名自动路由至对应厂商：

| 配置项 | 对应厂商 |
|--------|----------|
| `api_key` | Agnes AI（全局默认） |
| `deepseek_api_key` | DeepSeek |
| `text_api_key` | 文本模型专用（兼容旧版，优先使用厂商独立 Key） |

Key 回退链：`{vendor}_api_key` → `text_api_key` → `api_key`
