# Agnes AI Studio

一个基于 Agnes AI API 的图片和视频生成可视化工具，提供美观的 Web 操作界面。

## 功能

- **🖼 文生图** - 通过文本描述生成高质量图片
- **🎨 图生图** - 基于参考图片进行风格转换和编辑
- **🎬 文生视频** - 通过文本描述生成视频
- **🖼→🎬 图生视频** - 让静态图片动起来
- **📋 任务管理** - 实时查看视频生成任务状态和进度
- **⚙ API Key 管理** - 可视化配置和管理 API Key

---

## 🚀 方式一：使用打包好的 EXE（推荐，无需安装任何环境）

适合**没有 Python 环境**的用户，直接双击运行。

### 使用步骤

1. 将 `dist/Agnes-AI-Studio.exe` 复制到任意目录
2. **双击运行** `Agnes-AI-Studio.exe`
3. 浏览器会自动打开 `http://127.0.0.1:5000`
4. 点击右上角「⚙ 设置」，输入 API Key 即可使用

> 💡 **分享给他人**：只需发送这一个 `Agnes-AI-Studio.exe` 文件（约 15MB）即可！

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

访问 [Agnes AI 平台](https://platform.agnes-ai.com) 注册账号并获取免费 API Key。

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

### 图片生成模型

| 模型 | 用途 |
|------|------|
| `agnes-image-2.1-flash` | 文生图 |
| `agnes-image-2.0-flash` | 图生图 / 图片编辑 |

### 视频生成模型

| 模型 | 用途 |
|------|------|
| `agnes-video-v2.0` | 文生视频 / 图生视频 |

### 视频参数说明

- **num_frames**: 帧数，需满足 8n+1 格式，最大 ≤441
- **frame_rate**: 帧率，范围 1-60
- **时长公式**: seconds = num_frames / frame_rate
- 推荐配置: 121帧/24fps ≈ 5秒, 241帧/24fps ≈ 10秒

## 项目结构

```
agnes-ai-studio/
├── app.py                  # Flask 后端服务
├── requirements.txt        # Python 依赖
├── start.bat / start.sh    # 启动脚本
├── build.bat               # 打包脚本
├── Agnes-AI-Studio.spec    # PyInstaller 配置
├── version_info.txt        # EXE 版本信息
├── static/
│   └── index.html          # 前端 Web 界面
└── dist/
    └── Agnes-AI-Studio.exe # 打包后的独立可执行文件
```

## 技术栈

- **后端**: Python Flask + Requests
- **前端**: 原生 HTML/CSS/JS (无需额外框架)
- **打包**: PyInstaller (单文件 EXE)
- **API**: Agnes AI (OpenAI 兼容协议)
