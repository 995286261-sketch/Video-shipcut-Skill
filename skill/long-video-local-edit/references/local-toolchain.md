# Local Toolchain

本文件描述的是运行时契约，不代表这些工具已经随 Skill 一起打包。交付给新电脑时，必须同时提供检查结果；不要依赖开发机的历史安装状态。完整的便携性和许可证规则见 `skill/p0-c-pipeline/references/runtime-dependencies.md`。

This Skill uses a shared user-level toolchain. Do not copy executables or models into a project material pack or output workspace.

## Required paths

| Environment variable | Expected path | Purpose |
| --- | --- | --- |
| `P0C_TOOLCHAIN_ROOT` | Optional shared tool root | Shared tool root |
| `P0C_FFMPEG_HOME` | Optional FFmpeg directory | `ffmpeg` and `ffprobe`; otherwise resolve from `PATH` |
| `P0C_PYTHON_HOME` | Optional controlled Python 3.10+ directory | Controlled Python runtime |
| `P0C_FASTER_WHISPER_HOME` | Optional Faster-Whisper runtime directory | Offline transcription runtime |
| `P0C_FASTER_WHISPER_MODEL_HOME` | Optional model cache directory | Cached offline models |

On Windows the existing `D:\WorkTool` layout remains supported. On macOS/Linux, install Python 3.10+ and FFmpeg with the team's normal package manager and make them available on `PATH`, or set the variables above. New terminals inherit environment changes; an already-open terminal may need to be restarted.

`local_transcribe.py` automatically prepends `P0C_FASTER_WHISPER_HOME` when importing Faster-Whisper and resolves a uniquely cached model snapshot beneath `P0C_FASTER_WHISPER_MODEL_HOME`. Do not add `PYTHONPATH` manually in normal use. If either directory is absent or no unique cached snapshot exists, stop on the script's structured `blocked` response; do not install, download, or refresh anything during a media run.

## Doctor checks

Before processing media, verify these paths and run:

```powershell
python scripts/local_edit_engine.py doctor
ffmpeg -version
ffprobe -version
```

Do not download a replacement tool merely because the current terminal cannot resolve it. First check `PATH`, the variables above, and restart the terminal. The local Faster-Whisper model remains offline-only; do not add model download flags to the workflow.
