#!/usr/bin/env python3
"""Inspect a local video and sample frames; this is not full video comprehension.

Requires Python 3, Pillow, and ffmpeg/ffprobe on PATH. No network or model calls.
"""

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def seconds(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite, nonnegative number of seconds")
    return number


def timestamp(value):
    milliseconds = round(value * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def fraction(value, fallback=1.0):
    try:
        numerator, denominator = str(value).replace(":", "/").split("/")
        result = float(numerator) / float(denominator)
        return result if math.isfinite(result) and result > 0 else fallback
    except (ValueError, ZeroDivisionError):
        return fallback


def load_font(ImageFont, explicit, size):
    candidates = [explicit] if explicit else [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except (OSError, ValueError):
            if explicit:
                raise ValueError(f"Cannot load --font: {explicit}")
    return ImageFont.load_default()


def make_contact_sheet(Image, ImageDraw, ImageFont, output, frames, font_path):
    columns = min(4, len(frames))
    cell_width, cell_height, header_height = 250, 355, 50
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (columns * cell_width, header_height + rows * cell_height), "#171a20")
    draw = ImageDraw.Draw(sheet)
    font = load_font(ImageFont, font_path, 17)
    draw.text((12, 12), "SAMPLED FRAMES | seek times", fill="white", font=font)
    for index, frame in enumerate(frames):
        x, y = (index % columns) * cell_width, header_height + (index // columns) * cell_height
        draw.text((x + 8, y + 5), frame["timestamp"], fill="white", font=font)
        with Image.open(output / frame["file"]) as original:
            thumb = original.convert("RGB")
        thumb.thumbnail((cell_width - 16, cell_height - 40), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (x + (cell_width - thumb.width) // 2, y + 32))
    sheet.save(output / "contact_sheet.jpg", quality=92)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="new or empty output directory")
    sampling = parser.add_mutually_exclusive_group()
    sampling.add_argument("--samples", type=positive_int, default=16, help="uniform samples (default: at most 16; maximum: 256)")
    sampling.add_argument("--at", nargs="+", type=seconds, metavar="SECONDS", help="explicit seek times, each in [0, video duration)")
    parser.add_argument("--max-edge", type=positive_int, default=720, help="maximum extracted-frame edge; no upscaling (default: 720)")
    parser.add_argument("--audio", action="store_true", help="also extract the entire first audio stream as mono 16 kHz WAV, if present")
    parser.add_argument("--font", type=Path, help="optional TrueType/OpenType contact-sheet font")
    args = parser.parse_args()
    source, output = args.video.expanduser().resolve(), args.out.expanduser().resolve()
    if not source.is_file():
        parser.error(f"Video does not exist or is not a file: {source}")
    if args.samples > 256 or (args.at and len(args.at) > 256):
        parser.error("At most 256 samples are supported per run")
    if args.max_edge > 16384:
        parser.error("--max-edge must not exceed 16384")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error(f"Refusing to overwrite a nonempty output directory or file: {output}")
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        parser.error("Missing dependency: Pillow. Install it in the selected Python environment.")
    for binary in ("ffprobe", "ffmpeg"):
        if not shutil.which(binary):
            parser.error(f"Missing dependency on PATH: {binary}")
    try:
        load_font(ImageFont, args.font, 17)
    except ValueError as error:
        parser.error(str(error))

    output.mkdir(parents=True, exist_ok=True)
    diagnostics = {"source": str(source), "status": "running", "commands": []}
    manifest = {
        "source": str(source),
        "notice": "Sampled frames only, not full video comprehension. Times are requested seek positions; decoded frame timestamps can differ.",
        "frames": [],
    }

    def run(arguments):
        result = subprocess.run(arguments, capture_output=True, text=True, encoding="utf-8", errors="replace")
        diagnostics["commands"].append({"arguments": arguments, "returncode": result.returncode, "stderr": result.stderr})
        write_json(output / "diagnostics.json", diagnostics)
        if result.returncode:
            raise RuntimeError(f"{Path(arguments[0]).name} failed (exit {result.returncode}): {result.stderr.strip()}")
        return result.stdout

    try:
        raw = json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)]))
        write_json(output / "metadata.json", {"source": str(source), "raw_ffprobe": raw})
        streams = raw.get("streams", [])
        video = next((stream for stream in streams if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")), None)
        if video is None:
            raise ValueError("Input has no usable video stream")
        duration = None
        for candidate in (video.get("duration"), raw.get("format", {}).get("duration")):
            try:
                number = float(candidate)
                if math.isfinite(number) and number > 0:
                    duration = number
                    break
            except (TypeError, ValueError):
                pass
        if duration is None:
            raise ValueError("Cannot determine a positive video duration")
        width, height = int(video.get("width", 0)), int(video.get("height", 0))
        if width <= 0 or height <= 0:
            raise ValueError("Video stream has invalid dimensions")
        rotation = float(next((item["rotation"] for item in video.get("side_data_list", []) if "rotation" in item), video.get("tags", {}).get("rotate", 0)))
        if not math.isfinite(rotation):
            raise ValueError("Video stream has an invalid rotation")
        sar = fraction(video.get("sample_aspect_ratio", "1:1"))
        angle = math.radians(rotation)
        display_width = max(1, round(abs(width * sar * math.cos(angle)) + abs(height * math.sin(angle))))
        display_height = max(1, round(abs(width * sar * math.sin(angle)) + abs(height * math.cos(angle))))
        audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        metadata = {
            "source": str(source), "duration": duration, "has_audio": audio is not None,
            "video_stream_index": video["index"], "encoded_width": width, "encoded_height": height,
            "rotation": rotation, "sample_aspect_ratio": sar,
            "display_width": display_width, "display_height": display_height,
            "audio_extraction": "not_requested" if not args.audio else ("pending" if audio else "no_audio_stream"),
            "raw_ffprobe": raw,
        }
        write_json(output / "metadata.json", metadata)
        if args.at:
            positions = args.at
            if any(position >= duration for position in positions):
                raise ValueError(f"Every --at value must be less than video duration ({duration:.9f} seconds)")
        else:
            fps = fraction(video.get("avg_frame_rate", "0/0"), fallback=0)
            count = args.samples
            if fps:
                count = min(count, max(1, math.ceil(duration * fps)))
            last = duration - min(duration / 2, 1 / fps if fps else 0.04)
            positions = [0.0] if count == 1 else [last * index / (count - 1) for index in range(count)]
        scale = min(1, args.max_edge / max(display_width, display_height))
        frame_width, frame_height = max(1, round(display_width * scale)), max(1, round(display_height * scale))
        manifest["sampling"] = "explicit" if args.at else "uniform"
        write_json(output / "manifest.json", manifest)
        for index, position in enumerate(positions, 1):
            target = output / f"frame_{index:03d}_{round(position * 1000):09d}ms.jpg"
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-ss", str(position), "-i", str(source), "-map", f"0:{video['index']}", "-frames:v", "1", "-vf", f"scale={frame_width}:{frame_height}:flags=lanczos,setsar=1", "-q:v", "2", str(target)])
            with Image.open(target) as frame:
                frame.verify()
            manifest["frames"].append({"requested_seconds": position, "timestamp": timestamp(position), "file": target.name, "width": frame_width, "height": frame_height})
            write_json(output / "manifest.json", manifest)
        make_contact_sheet(Image, ImageDraw, ImageFont, output, manifest["frames"], args.font)
        if args.audio and audio:
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(source), "-map", f"0:{audio['index']}", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output / "audio_mono_16k.wav")])
            metadata["audio_extraction"] = "audio_mono_16k.wav"
            write_json(output / "metadata.json", metadata)
        diagnostics["status"] = "complete"
        print(json.dumps({"output": str(output), "duration": duration, "frames": len(manifest["frames"]), "has_audio": audio is not None, "audio_extraction": metadata["audio_extraction"], "notice": manifest["notice"]}, ensure_ascii=True))
        return 0
    except Exception as error:
        diagnostics.update(status="failed", error=f"{type(error).__name__}: {error}")
        write_json(output / "error.json", {"error": diagnostics["error"], "source": str(source)})
        print(f"Inspection failed: {error}\nPartial results and diagnostics preserved in: {output}", file=sys.stderr)
        return 1
    finally:
        write_json(output / "diagnostics.json", diagnostics)


if __name__ == "__main__":
    sys.exit(main())
