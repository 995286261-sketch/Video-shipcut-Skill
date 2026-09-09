# 故障样本（真实发生与处理）

1. **旁白响度归一受限**：源 TTS 积分 −23.9 LUFS / 真峰 +0.5 dBFS（PLR 24.4dB），线性 loudnorm 与动态 loudnorm 均被 TP 限制在 −16 左右；最终采用 acompressor(8:1)+loudnorm 链达 −15.2 LUFS / −1.5 dBFS，接受并登记为警告。
2. **封面字体路径**：`/System/Library/Fonts/PingFang.ttc`、`Songti.ttc` 在本机不存在（Songti 实际在 Supplemental/），drawtext 首次失败；改用 `Supplemental/Songti.ttc` 成功。
3. **G3 包装决定时码错误**：章节卡「2:05.00 / 2:38.60」超出 103.32s 成片时间轴（误写源片时码），且 g4_assemble 不支持章节卡图层；经 G4 播放复核卡报告，用户选择 A（接受无章节卡版本）。
4. **soxr 重采样器不可用**：尝试过采样域真峰限制时 `resampler=soxr` 报错，改用默认重采样器后仍受 TP 限制，最终走压缩+归一路径（见 1）。
