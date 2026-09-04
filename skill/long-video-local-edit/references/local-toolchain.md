# Local Toolchain

本文件描述的是运行时契约，不代表这些工具已经随 Skill 一起打包。交付给新电脑时，必须同时提供检查结果；不要依赖开发机的历史安装状态。完整的便携性和许可证规则见 `skill/video-shipcut-pipeline/references/runtime-dependencies.md`。

This Skill uses a user-level Windows toolchain. Install shared executables beneath `D:\WorkTool`; do not copy binaries into a project material pack or output workspace.

## Required paths

| Environment variable | Expected path | Purpose |
| --- | --- | --- |
| `SHIPCUT_TOOLCHAIN_ROOT` | `D:\WorkTool` | Shared tool root |
| `SHIPCUT_FFMPEG_HOME` | `D:\WorkTool\ffmpeg\releases\7.1.1\ffmpeg-7.1.1-essentials_build\bin` | `ffmpeg` and `ffprobe` |
| `SHIPCUT_PYTHON_HOME` | `D:\WorkTool\Python312` | Controlled Python runtime |
| `SHIPCUT_FASTER_WHISPER_HOME` | `D:\WorkTool\faster-whisper` | Offline transcription runtime |
| `SHIPCUT_FASTER_WHISPER_MODEL_HOME` | `D:\WorkTool\faster-whisper-models` | Cached offline models |

`SHIPCUT_FFMPEG_HOME`, `SHIPCUT_PYTHON_HOME`, and `SHIPCUT_PYTHON_HOME\Scripts` must also be present in the user `Path`. New terminals inherit user-level environment changes; an already-open terminal must be restarted.

`local_transcribe.py` automatically prepends `SHIPCUT_FASTER_WHISPER_HOME` when importing Faster-Whisper and resolves a uniquely cached model snapshot beneath `SHIPCUT_FASTER_WHISPER_MODEL_HOME`. Do not add `PYTHONPATH` manually in normal use. If either directory is absent or no unique cached snapshot exists, stop on the script's structured `blocked` response; do not install, download, or refresh anything during a media run.

## Doctor checks

Before processing media, verify these paths and run:

```powershell
python scripts/local_edit_engine.py doctor
ffmpeg -version
ffprobe -version
```

Do not download a replacement tool merely because the current terminal cannot resolve it. First check the variables above and restart the terminal. The local Faster-Whisper model remains offline-only; do not add model download flags to the workflow.
