# P0-C 工具链安装与检查

把 Skill 交给新使用者时，先阅读 `toolchain-manifest.json`，再按本机许可和组织政策安装。安装工具不等于授权素材、音乐、TTS 声音或网站账号授权。

## 可安装项目

- Python 3.12：由使用者安装并设置 `P0C_PYTHON_HOME`。
- FFmpeg/FFprobe：使用者安装或提供经许可的便携版，并设置 `P0C_FFMPEG_HOME`。
- Faster-Whisper 运行时：使用者提供离线运行时并设置 `P0C_FASTER_WHISPER_HOME`。
- Faster-Whisper 模型：单独确认模型许可并设置 `P0C_FASTER_WHISPER_MODEL_HOME`。

## 不自动安装项目

模型缓存、TTS 音色、浏览器 Cookie、客户素材、BGM 和任何授权不明文件不得由 Skill 静默下载。缺少其中任一项时，相关节点返回 `blocked`，并说明缺少的能力。

## 检查

```powershell
python skill/long-video-local-edit/scripts/local_edit_engine.py doctor
ffmpeg -version
ffprobe -version
```

G2 另需确认 Faster-Whisper 运行时和唯一的本地模型快照；G4 另需确认已通过 G2 试听的实际 TTS 来源。检查结果应随项目交接保存，但不把个人路径、账号或 Cookie 写入交付包。
