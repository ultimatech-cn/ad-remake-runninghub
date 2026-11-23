"""Extract candidate hard cuts and evidence frames from a local video."""
import argparse
import json
import re
import subprocess
from pathlib import Path


def ffmpeg(binary, *args):
    result = subprocess.run(
        [binary, "-hide_banner", "-nostdin", *args], capture_output=True, text=True
    )
    if result.returncode:
        raise SystemExit(result.stderr.strip())
    return result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--threshold", type=float, default=0.30)
    args = parser.parse_args()
    if not 0 < args.threshold < 1:
        parser.error("--threshold must be between 0 and 1")
    video = str(args.video.resolve(strict=True))
    log = ffmpeg(
        args.ffmpeg, "-i", video, "-map", "0:v:0", "-an",
        "-vf", f"scale=360:-2,select='gt(scene,{args.threshold})',showinfo",
        "-f", "null", "-"
    )
    duration_match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", log)
    if not duration_match:
        raise SystemExit("Video duration unavailable. Use timestamped frames instead.")
    hours, minutes, seconds = map(float, duration_match.groups())
    duration = hours * 3600 + minutes * 60 + seconds
    if duration <= 0:
        raise SystemExit("Video duration must be positive.")
    cuts = sorted({float(value) for value in re.findall(r"pts_time:([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s", log)
                   if 0 < float(value) < duration})
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {"source": args.video.name, "container_duration_s": duration,
                "scene_threshold": args.threshold, "candidate_cuts_s": cuts,
                "audio_stream_detected": bool(re.search(r"Stream .*Audio:", log)),
                "intervals": []}
    boundaries = [0.0, *cuts, duration]
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), 1):
        samples = []
        for fraction, label in ((0.15, "early"), (0.5, "mid"), (0.85, "late")):
            timestamp = start + (end - start) * fraction
            path = args.output / f"{index:02}-{label}.jpg"
            ffmpeg(args.ffmpeg, "-ss", f"{timestamp:.6f}", "-i", video,
                   "-map", "0:v:0", "-frames:v", "1", "-vf", "scale=540:-2",
                   "-q:v", "3", str(path))
            if path.is_file():
                samples.append({"seek_s": round(timestamp, 4), "file": path.name})
        manifest["intervals"].append({"start_s": start, "end_s": end, "samples": samples})
    manifest_path = args.output / "evidence.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print(manifest_path)


if __name__ == "__main__":
    main()
