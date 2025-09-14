# 视频剪辑工具 (Video Editor Tool)

一个基于PySide6的现代化视频剪辑工具，支持视频剪切、自动字幕生成和高质量编码输出。

## ✨ 功能特性

- 🎬 **智能视频剪切** - 精确选择并删除不需要的视频片段
- 🎯 **高质量编码** - 使用优化的FFmpeg参数，保持最佳画质
- ⚡ **硬件加速** - 自动检测并支持NVIDIA NVENC、AMD AMF、Intel QSV硬件编码
- 🎤 **自动字幕生成** - 集成Whisper语音识别，自动生成字幕
- 🖥️ **现代化界面** - 基于PySide6的直观GUI界面
- 📊 **实时进度显示** - 处理进度和预计完成时间

## 🛠️ 技术栈

- **GUI框架**: PySide6
- **视频处理**: FFmpeg + MoviePy
- **语音识别**: Faster-Whisper
- **硬件加速**: NVIDIA NVENC / AMD AMF / Intel QSV
- **编码优化**: libx264 with高质量参数

## 📦 安装要求

### 系统要求
- Python 3.8+
- FFmpeg (必须安装并添加到PATH)
- 推荐使用NVIDIA显卡以获得硬件加速

### Python依赖
安装所有依赖：
```bash
pip install -r requirements.txt
```

或者手动安装核心依赖：
```bash
pip install PySide6 moviepy faster-whisper imageio-ffmpeg python-vlc
```

### FFmpeg安装
**Windows用户**:
```bash
# 使用 chocolatey
choco install ffmpeg

# 或从官网下载: https://ffmpeg.org/download.html
```

**Linux用户**:
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# CentOS/RHEL
sudo yum install ffmpeg
```

## 🚀 快速开始

1. **克隆仓库**
```bash
git clone https://github.com/engsd/jiankoubo.git
cd jiankoubo
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **运行程序**
```bash
python main.py
```

## 📖 使用指南

### 主界面功能
1. **视频导入** - 点击"选择视频文件"按钮导入视频
2. **片段选择** - 在时间轴上选择要删除的片段
3. **预览播放** - 使用播放控制按钮预览视频
4. **参数设置** - 调整输出质量和字幕选项
5. **开始处理** - 点击"开始处理"按钮执行剪辑操作

### 编码质量设置
程序自动使用高质量编码参数：
- **CPU编码**: CRF 16, preset slower, 20000k比特率
- **NVENC编码**: CRF 16, preset medium, 20000k比特率
- **其他硬件编码**: CRF 16, preset slow, 20000k比特率

### 字幕生成
- 自动检测语音并生成字幕文件
- 支持中英文等多种语言
- 可调整字幕位置和样式

## ⚙️ 配置文件

编辑 `video_editor_config.json` 来自定义设置：
```json
{
    "default_output_dir": "output",
    "ffmpeg_path": "ffmpeg",
    "whisper_model": "small",
    "hardware_acceleration": true,
    "default_bitrate": "20000k"
}
```

## 🔧 开发说明

### 项目结构
```
video-editor/
├── main.py              # 主程序入口
├── main_window.py       # GUI界面实现
├── processing.py        # 视频处理核心逻辑
├── requirements.txt     # 依赖列表
├── video_editor_config.json  # 配置文件
└── README.md           # 项目说明
```

### 核心模块
- **main_window.py** - PySide6界面组件和事件处理
- **processing.py** - FFmpeg命令构建、硬件加速检测、视频处理逻辑
- **VideoProcessor类** - 多线程视频处理，支持进度回调

## 🐛 常见问题

### Q: 程序无法找到FFmpeg
A: 请确保FFmpeg已安装并添加到系统PATH环境变量

### Q: 硬件加速不工作
A: 检查显卡驱动是否最新，支持的编码器：NVIDIA NVENC, AMD AMF, Intel QSV

### Q: 处理速度慢
A: 尝试启用硬件加速或使用更小的Whisper模型

### Q: 输出文件太大
A: 在配置文件中调整比特率参数（如改为"15000k"）

## 📄 许可证

本项目采用MIT许可证。详见LICENSE文件。

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目！

## 📞 支持

如有问题请提交GitHub Issue或联系维护者。

---

**享受视频剪辑的乐趣！** 🎉