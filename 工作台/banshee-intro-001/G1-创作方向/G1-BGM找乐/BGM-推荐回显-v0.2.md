# BGM 推荐回显 v0.2

> ⚠ 侵权风险：6/7 条候选未清权（uncleared-platform-catalog，网易云试听选型）。平台曲库授权仅覆盖端内播放——未登记而将其用于成片即构成侵权。本池仅限 internal_test 选型；挑曲后整轨必须经官方渠道取得并经 music_register_candidate.py 登记真实许可后方可进剪辑计划。对外分发项目在任何清权完成前不得使用这些曲目。

- 画像：时长 ≥160s｜BPM [110.7, 135.4]｜通过线 0.7｜通过 6/7（充分性阈值 3）
- 锚定：以参照曲风格简报打分（锚 BPM 123.05＋能量曲线相似度，含半速/倍速亲缘容差）

| # | 曲目 | BPM | 时长 | 响度 | 分 | 侵权风险 | 注记 |
|---|---|---|---|---|---|---|---|
| 1 | 蝙蝠侠Stage-1（工业电子） | 129.2 | 6:03.160 | -17.3 | 0.793 | ⚠ 未清权 | decode_via_analysis、bpm_proximity=0.8334、energy_similarity=0.5405、tags 0/5、uncleared_internal_test_only |
| 2 | 悬空城（工业电子） | 129.2 | 4:04.960 | -12.4 | 0.781 | ⚠ 未清权 | decode_via_analysis、bpm_proximity=0.8334、energy_similarity=0.452、tags 0/5、uncleared_internal_test_only |
| 3 | 弥渡山歌Phonk House | 123.05 | 2:05.735 | -6.0 | 0.768 | ⚠ 未清权 | decode_via_analysis、shorter_than_target、bpm_proximity=1.0、energy_similarity=0.5946、tags 0/5、uncleared_internal_test_only |
| 4 | Gone Bad(Phonk) | 117.45 | 2:28.000 | -7.1 | 0.750 | ⚠ 未清权 | decode_via_analysis、shorter_than_target、bpm_proximity=0.8483、energy_similarity=0.3942、tags 0/5、uncleared_internal_test_only |
| 5 | LOW-PHONK | 112.35 | 2:57.875 | -10.2 | 0.749 | — | decode_via_analysis、bpm_proximity=0.7101、energy_similarity=0.4615、tags 0/5 |
| 6 | Devil Game (Phonk) | 117.45 | 2:08.036 | -6.3 | 0.716 | ⚠ 未清权 | decode_via_analysis、shorter_than_target、bpm_proximity=0.8483、energy_similarity=0.4718、tags 0/5、uncleared_internal_test_only |
| 7 | 相对论 (工业电子版) | 143.55 | 2:08.894 | -13.6 | 0.591 | ⚠ 未清权 | decode_via_analysis、shorter_than_target、bpm_proximity=0.4447、energy_similarity=0.3409、tags 0/5、uncleared_internal_test_only |

- 未分析隔离：7 条（先跑 music_analyze 再打分）。

- 分数只是机器的适配度排序，最终取舍在人耳：试听件路径见候选清单 `previewPath`；挑曲后必须登记，未登记不得进剪辑计划。
