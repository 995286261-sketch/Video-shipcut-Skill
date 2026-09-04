#!/usr/bin/env python3
"""Render G4 video segments from G4-可编辑工程-v0.2.json using FFmpeg."""
import argparse
import json
import subprocess
from pathlib import Path

def fail(message): raise ValueError(message)
def load(path): return json.loads(path.read_text(encoding="utf-8-sig"))
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--manifest",required=True,type=Path); parser.add_argument("--source-pack",required=True,type=Path); parser.add_argument("--output-dir",required=True,type=Path); parser.add_argument("--width",type=int,default=1920); parser.add_argument("--height",type=int,default=1080); parser.add_argument("--fps",type=int,default=24); parser.add_argument("--crop-bottom-ratio",type=float,default=.14); parser.add_argument("--dry-run",action="store_true"); args=parser.parse_args()
    data=load(args.manifest)
    if data.get("status") != "prepared_for_render": fail("manifest is not prepared_for_render")
    if not (0 <= args.crop_bottom_ratio < 1): fail("crop-bottom-ratio must be in [0,1)")
    args.output_dir.mkdir(parents=True,exist_ok=True)
    commands=[]
    for segment in data.get("segments",[]):
        source=args.source_pack/segment["source"]["relativePath"]
        output=args.output_dir/segment["output"]["filename"]
        if not source.is_file(): fail(f"missing source {source}")
        duration=(segment["timeline"]["endMs"]-segment["timeline"]["startMs"])/1000
        source_duration=(segment["source"]["endMs"]-segment["source"]["startMs"])/1000
        if duration > source_duration:
            fail(f"output duration exceeds approved source range for {segment.get('segmentId')}")
        crop=f"crop=iw:trunc(ih*{1-args.crop_bottom_ratio}):0:0,"
        vf=crop+f"scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2:color=0x101418,setsar=1,fps={args.fps}"
        image_input = source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        cmd=["ffmpeg","-y"]
        if image_input:
            cmd += ["-loop", "1", "-i", str(source)]
        else:
            cmd += ["-ss",str(segment["source"]["startMs"]/1000),"-i",str(source)]
        cmd += ["-t",str(duration),"-map","0:v:0","-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","20","-an","-movflags","+faststart",str(output)]
        commands.append(cmd)
    if args.dry_run:
        print(json.dumps({"status":"planned","commands":commands},ensure_ascii=True)); return 0
    for cmd in commands: subprocess.run(cmd,check=True)
    print(json.dumps({"status":"rendered","segments":len(commands),"outputDir":str(args.output_dir)},ensure_ascii=True)); return 0
if __name__=="__main__":
    try: raise SystemExit(main())
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        print(json.dumps({"status":"failed","error":str(error)},ensure_ascii=True)); raise SystemExit(2)
