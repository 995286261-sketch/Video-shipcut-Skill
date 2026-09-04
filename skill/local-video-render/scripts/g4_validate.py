#!/usr/bin/env python3
"""Validate a generated G4 editable manifest and ChatCut handoff package."""
import argparse
import json
import subprocess
from pathlib import Path

def fail(message): raise ValueError(message)
def load(path): return json.loads(path.read_text(encoding="utf-8-sig"))
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--manifest", required=True, type=Path); parser.add_argument("--handoff-dir", type=Path); parser.add_argument("--segments-dir", type=Path); parser.add_argument("--width",type=int); parser.add_argument("--height",type=int); parser.add_argument("--fps",type=float,default=24); args=parser.parse_args()
    if bool(args.width) != bool(args.height): fail("--width and --height must be supplied together")
    data=load(args.manifest)
    if data.get("schemaVersion") != "0.2" or data.get("status") != "prepared_for_render": fail("invalid G4 editable manifest")
    segments=data.get("segments", [])
    if data.get("segmentCount") != len(segments) or not segments: fail("segment count mismatch")
    cursor=0
    source_ranges={}
    for index, segment in enumerate(segments,1):
        if segment.get("order") != index or segment.get("timeline",{}).get("startMs") != cursor: fail("segments must be ordered and contiguous")
        source=segment.get("source",{}); output=segment.get("output",{}); timeline=segment.get("timeline",{})
        if not isinstance(timeline.get("endMs"), int) or timeline["endMs"] <= timeline.get("startMs", -1): fail("segment timeline duration must be positive")
        if not source.get("relativePath") or not source.get("sha256") or not isinstance(source.get("startMs"), int) or not isinstance(source.get("endMs"), int) or source["endMs"]<=source["startMs"]: fail("segment lacks source provenance")
        source_duration=source["endMs"]-source["startMs"]
        timeline_duration=timeline["endMs"]-timeline["startMs"]
        mapping=segment.get("mapping",{})
        if mapping.get("mode", "one_to_one") not in {"one_to_one", "trim"}: fail("unsupported source/output mapping mode")
        if mapping.get("mode", "one_to_one") == "one_to_one" and source_duration != timeline_duration: fail("one_to_one source/output duration mismatch")
        if mapping.get("mode", "one_to_one") == "trim" and timeline_duration > source_duration: fail("trim output cannot exceed source duration")
        key=source["sha256"].lower(); existing_ranges=source_ranges.setdefault(key, [])
        for prior_start, prior_end, prior_id in existing_ranges:
            if source["startMs"] < prior_end and source["endMs"] > prior_start:
                fail(f"source range overlap for {prior_id} and {segment.get('segmentId')}")
        existing_ranges.append((source["startMs"],source["endMs"],segment.get("segmentId")))
        if output.get("audio") != "excluded" or output.get("filename") != f"seg-{index:03d}.mp4": fail("segment output contract failed")
        cursor=timeline["endMs"]
    if cursor != data.get("timelineDurationMs"): fail("timeline duration mismatch")
    if args.handoff_dir:
        handoff=args.handoff_dir
        required=["README.md","asset-manifest.json","subtitles-draft.srt","approved-script.txt"]
        missing=[name for name in required if not (handoff/name).is_file()]
        if missing: fail("handoff missing: "+", ".join(missing))
        assets=load(handoff/"asset-manifest.json").get("assets",[])
        names={item.get("filename") for item in assets}
        expected={segment["output"]["filename"] for segment in segments}
        if not expected.issubset(names): fail("handoff does not declare every editable segment")
        if any("粗剪" in str(name) for name in names): fail("handoff must not declare flattened rough cut as timeline asset")
    if args.segments_dir:
        detected_canvas=None
        for segment in segments:
            file=args.segments_dir/segment["output"]["filename"]
            if not file.is_file(): fail("missing rendered segment: "+file.name)
            probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration:stream=codec_type,width,height,r_frame_rate","-of","json",str(file)],capture_output=True,text=True,encoding="utf-8",errors="replace",check=True)
            meta=json.loads(probe.stdout); streams=meta.get("streams",[]); video=next((s for s in streams if s.get("codec_type")=="video"),None)
            if not video: fail("missing video stream: "+file.name)
            actual_canvas=(video.get("width"),video.get("height"))
            expected_canvas=(args.width,args.height) if args.width else detected_canvas
            if expected_canvas and actual_canvas!=expected_canvas: fail("bad video profile: "+file.name)
            if detected_canvas is None: detected_canvas=actual_canvas
            if any(s.get("codec_type")=="audio" for s in streams): fail("source audio leaked: "+file.name)
            expected=(segment["timeline"]["endMs"]-segment["timeline"]["startMs"])/1000
            if abs(float(meta["format"]["duration"])-expected)>.15: fail("bad duration: "+file.name)
    print(json.dumps({"status":"valid","segments":len(segments),"timelineDurationMs":cursor}, ensure_ascii=True)); return 0
if __name__=="__main__":
    try: raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status":"invalid","error":str(error)},ensure_ascii=True)); raise SystemExit(2)
