#!/usr/bin/env python3
"""Render G4 video segments from G4-可编辑工程-v0.2.json using FFmpeg."""
import argparse
import json
import subprocess
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def fail(message):
    raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def probe_canvas(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    streams = json.loads(result.stdout).get("streams", [])
    if not streams or not streams[0].get("width") or not streams[0].get("height"):
        fail(f"cannot determine source canvas: {path}")
    return int(streams[0]["width"]), int(streams[0]["height"])


def build_mask_filters(masks, segment, canvas):
    """G3-approved source-caption masking executed per segment (issue: 遮蔽窗口只存在于批准表,
    G4 需要机器消费). Windows are output-timeline ms converted to slice-local seconds;
    pixel bands become ih ratios so the mask survives any target canvas."""
    filters = []
    out_start, out_end = segment["timeline"]["startMs"], segment["timeline"]["endMs"]
    for mask in masks:
        if mask.get("segmentId") != segment.get("segmentId"):
            continue
        start = max(int(mask["outputFromMs"]), out_start)
        end = min(int(mask["outputToMs"]), out_end)
        if end <= start:
            fail(f"mask {mask.get('maskId')} does not overlap segment {segment.get('segmentId')}")
        y0, y1 = mask["bandYpx"]
        if not (0 <= y0 < y1 <= canvas["height"]):
            fail(f"mask {mask.get('maskId')} band {y0}-{y1} outside contract canvas {canvas['height']}")
        r0 = y0 / canvas["height"]
        color = mask.get("color", "black")
        filters.append(
            f"drawbox=x=0:y=trunc(ih*{r0:.6f}):w=iw:h=ih-trunc(ih*{r0:.6f})"
            f":color={color}:t=fill:enable='between(t,{(start - out_start) / 1000:.3f},{(end - out_start) / 1000:.3f})'"
        )
    return filters


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-pack", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-mask", type=Path,
                        help="G4 source-caption masking contract (transcribed from the G3 approved table)")
    parser.add_argument(
        "--aspect-ratio-policy",
        choices=("preserve_source", "explicit"),
        default="preserve_source",
        help="preserve_source derives one common canvas from the first approved source",
    )
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--crop-bottom-ratio", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    data=load(args.manifest)
    if data.get("status") != "prepared_for_render": fail("manifest is not prepared_for_render")
    if not (0 <= args.crop_bottom_ratio < 1): fail("crop-bottom-ratio must be in [0,1)")
    masks, mask_canvas = [], {}
    if args.source_mask:
        mask_doc = load(args.source_mask)
        if mask_doc.get("node") != "G4" or mask_doc.get("schemaVersion") != "0.1":
            fail("--source-mask is not a G4 source-caption masking contract v0.1")
        if mask_doc.get("projectId") != data.get("projectId"):
            fail("mask contract projectId does not match the editable manifest")
        masks = mask_doc.get("masks") or []
        mask_canvas = mask_doc.get("canvas") or {}
        if not mask_canvas.get("height"):
            fail("mask contract lacks a canvas for ratio conversion")
        known = {segment.get("segmentId") for segment in data.get("segments", [])}
        for mask in masks:
            if mask.get("segmentId") not in known:
                fail(f"mask {mask.get('maskId')} targets unknown segment {mask.get('segmentId')}")
    if args.aspect_ratio_policy == "explicit":
        if not args.width or not args.height:
            fail("explicit aspect ratio policy requires --width and --height")
        target_width, target_height = args.width, args.height
    else:
        if args.width or args.height:
            fail("--width/--height require --aspect-ratio-policy explicit")
        first = next(iter(data.get("segments", [])), None)
        if not first:
            fail("manifest has no segments")
        first_source = args.source_pack / first["source"]["relativePath"]
        if not first_source.is_file():
            fail(f"missing source {first_source}")
        target_width, target_height = probe_canvas(first_source)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    # Issue 030: contract layout is <output-dir>/clean-segments/; never flatten segments
    # into the output root where different invocations drift the project structure.
    segments_out = args.output_dir / "clean-segments"
    segments_out.mkdir(parents=True,exist_ok=True)
    commands=[]
    outputs=[]
    for segment in data.get("segments",[]):
        source=args.source_pack/segment["source"]["relativePath"]
        output=segments_out/segment["output"]["filename"]
        if not source.is_file(): fail(f"missing source {source}")
        duration=(segment["timeline"]["endMs"]-segment["timeline"]["startMs"])/1000
        source_duration=(segment["source"]["endMs"]-segment["source"]["startMs"])/1000
        if duration > source_duration:
            fail(f"output duration exceeds approved source range for {segment.get('segmentId')}")
        crop=f"crop=iw:trunc(ih*{1-args.crop_bottom_ratio}):0:0,"
        vf=crop+f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=0x101418,setsar=1,fps={args.fps}"
        if masks:
            vf += "," + ",".join(build_mask_filters(masks, segment, mask_canvas))
        image_input = source.suffix.lower() in IMAGE_SUFFIXES
        cmd=["ffmpeg","-y"]
        if image_input:
            cmd += ["-loop", "1", "-i", str(source)]
        else:
            cmd += ["-ss",str(segment["source"]["startMs"]/1000),"-i",str(source)]
        cmd += ["-t",str(duration),"-map","0:v:0","-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","20","-an","-movflags","+faststart",str(output)]
        commands.append(cmd); outputs.append(output)
    if args.dry_run:
        print(json.dumps({"status":"planned","commands":commands},ensure_ascii=True)); return 0
    for cmd, output in zip(commands, outputs):
        subprocess.run(cmd,check=True)
        if not output.is_file() or output.stat().st_size == 0:
            fail(f"ffmpeg exited without producing {output.name}")
    print(json.dumps({
        "status":"rendered",
        "segments":len(commands),
        "outputDir":str(args.output_dir),
        "segmentsDir":str(segments_out),
        "aspectRatioPolicy": args.aspect_ratio_policy,
        "canvas": {"width": target_width, "height": target_height},
    },ensure_ascii=True)); return 0
if __name__=="__main__":
    try: raise SystemExit(main())
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        print(json.dumps({"status":"failed","error":str(error)},ensure_ascii=True)); raise SystemExit(2)
