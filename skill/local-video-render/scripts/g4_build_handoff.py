#!/usr/bin/env python3
"""Build a self-contained ChatCut editable handoff from a rendered G4 manifest."""
import argparse
import json
import shutil
from pathlib import Path

def load(path): return json.loads(path.read_text(encoding="utf-8-sig"))
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--manifest",required=True,type=Path); parser.add_argument("--segments-dir",required=True,type=Path); parser.add_argument("--narration",required=True,type=Path); parser.add_argument("--bgm",required=True,type=Path); parser.add_argument("--srt",required=True,type=Path); parser.add_argument("--script",required=True,type=Path); parser.add_argument("--cover",type=Path); parser.add_argument("--output-dir",required=True,type=Path); args=parser.parse_args()
    data=load(args.manifest); out=args.output_dir; out.mkdir(parents=True,exist_ok=True)
    required=[args.narration,args.bgm,args.srt,args.script,args.segments_dir]
    if not all(path.exists() for path in required): raise ValueError("missing handoff input")
    assets=[]
    for segment in data["segments"]:
        name=segment["output"]["filename"]; source=args.segments_dir/name
        if not source.is_file(): raise ValueError(f"missing rendered segment {name}")
        destination=out/name; shutil.copy2(source,destination)
        assets.append({"assetId":segment["segmentId"],"filename":name,"path":name,"type":"video","timeline":segment["timeline"],"source":segment["source"],"audio":"excluded","subtitleTreatment":segment["output"]["subtitleTreatment"]})
    for kind,path in (("narration",args.narration),("bgm",args.bgm)):
        shutil.copy2(path,out/path.name); assets.append({"assetId":kind,"filename":path.name,"path":path.name,"type":"audio","purpose":"independent "+kind+" track"})
    shutil.copy2(args.srt,out/"subtitles-draft.srt"); shutil.copy2(args.script,out/"approved-script.txt")
    if args.cover and args.cover.is_file(): shutil.copy2(args.cover,out/args.cover.name); assets.append({"assetId":"cover","filename":args.cover.name,"path":args.cover.name,"type":"image","purpose":"cover candidate only; do not auto-place"})
    (out/"asset-manifest.json").write_text(json.dumps({"schemaVersion":"0.2","projectId":data["projectId"],"purpose":"chatcut-editable-handoff","timelineDurationMs":data["timelineDurationMs"],"assets":assets,"rules":{"flattenedPreview":"not a ChatCut timeline source","video":"place seg-* in listed order on V1","narration":"place on A1","bgm":"place on A2","subtitles":"use subtitles-draft.srt only to correct editable caption cards"}},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    readme=f"# G4 ChatCut 可编辑交接包\n\n状态：`prepared_for_manual_chatcut_import`\n\n仅导入 `seg-*.mp4`、独立口播、独立 BGM 和本包字幕参考。不得将压平预览 MP4 放入时间线。\n\n- V1：按 `asset-manifest.json` 的 timeline 顺序放入 13 个分段画面。\n- A1：`{args.narration.name}`。\n- A2：`{args.bgm.name}`。\n- 字幕：从 A1 生成可编辑卡片，再用 `subtitles-draft.srt` / `approved-script.txt` 校对。\n\n计划时长：{data['timelineDurationMs']/1000:.3f}s；目标差异：{data['durationDeltaMs']/1000:+.3f}s。此差异必须由 G3 决策，不得在 G4 静默删段。\n"
    (out/"README.md").write_text(readme,encoding="utf-8")
    print(json.dumps({"status":"built","handoffDir":str(out),"segments":len(data["segments"])},ensure_ascii=True))
if __name__=="__main__":
    try: raise SystemExit(main())
    except (OSError,ValueError,json.JSONDecodeError) as error:
        print(json.dumps({"status":"invalid","error":str(error)},ensure_ascii=True)); raise SystemExit(2)
