"""
review_to_pp - Review Script to Premiere Pro XML + SRT converter

Input formats:
  1) Text  (.txt)  - Free-form review script with (HH:MM:SS) timestamps
  2) JSON  (.json) - Structured object
  3) CSV   (.csv)  - time,text columns

Output:
  - <name>_markers.xml  : Premiere Pro Final Cut Pro 7 XML (sequence + markers)
  - <name>_narration.srt: SRT subtitle for the narration

Usage:
  python review_to_pp.py input.txt
  python review_to_pp.py input.json -o D:\\output\\
  python review_to_pp.py input.csv --video D:\\videos\\1.mp4 --title "My Review"
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape as xml_escape


TIMESTAMP_RE = re.compile(r"\((\d{1,2}(?::\d{2}){1,2})\)")
META_LINE_RE = re.compile(r"^\[(?P<key>[^\]]+)\]\s*(?P<value>.+)$")


@dataclass
class Beat:
    time_sec: float
    text: str
    label: str = ""


@dataclass
class ReviewData:
    title: str = "Untitled Review"
    video_path: str = ""
    framerate: int = 30
    width: int = 1920
    height: int = 1080
    intro: str = ""
    beats: list[Beat] = field(default_factory=list)


def parse_timecode(tc: str) -> float:
    """Parse 'MM:SS' or 'HH:MM:SS' (or 'H:MM:SS') into seconds."""
    parts = tc.strip().split(":")
    if not all(p.isdigit() for p in parts):
        raise ValueError(f"Invalid timecode: {tc}")
    parts = [int(p) for p in parts]
    if len(parts) == 2:
        m, s = parts
        return m * 60 + s
    if len(parts) == 3:
        h, m, s = parts
        return h * 3600 + m * 60 + s
    raise ValueError(f"Unsupported timecode format: {tc}")


def format_srt_time(seconds: float) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def split_text_chunks(text: str, max_chars: int = 40) -> list[str]:
    """Wrap a long narration line into at most 2 visual lines of ~max_chars."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    # Split roughly in the middle on a Korean/space boundary.
    mid = len(text) // 2
    left = text[:mid].rfind(" ")
    right = text[mid:].find(" ")
    if left == -1 and right == -1:
        return [text[:mid], text[mid:]]
    if left == -1:
        cut = mid + right
    elif right == -1:
        cut = left
    else:
        cut = left if (mid - left) <= right else mid + right
    return [text[:cut].strip(), text[cut:].strip()]


def estimate_duration(text: str, chars_per_sec: float = 5.5) -> float:
    """Estimate narration duration for a Korean sentence."""
    n = len(text.strip())
    return max(2.0, n / chars_per_sec)


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #

def parse_text(path: Path) -> ReviewData:
    data = ReviewData()
    intro_lines: list[str] = []
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    in_intro = True
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        m = META_LINE_RE.match(stripped)
        if m:
            key = m.group("key").strip().lower()
            val = m.group("value").strip()
            if key in ("제목", "title"):
                data.title = val
            elif key in ("영상", "video", "video_path"):
                data.video_path = val
            elif key in ("프레임레이트", "framerate", "fps"):
                data.framerate = int(val)
            elif key in ("해상도", "resolution"):
                if "x" in val.lower():
                    w, h = val.lower().split("x", 1)
                    data.width, data.height = int(w.strip()), int(h.strip())
            continue

        ts = TIMESTAMP_RE.search(stripped)
        if ts:
            in_intro = False
            time_sec = parse_timecode(ts.group(1))
            text_after = TIMESTAMP_RE.sub("", stripped, count=1).strip()
            data.beats.append(Beat(time_sec=time_sec, text=text_after))
            continue

        if in_intro:
            intro_lines.append(stripped)
        else:
            if data.beats:
                data.beats[-1].text = (data.beats[-1].text + " " + stripped).strip()

    data.intro = " ".join(intro_lines).strip()
    return data


def parse_json(path: Path) -> ReviewData:
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = ReviewData()
    data.title = raw.get("title", data.title)
    data.video_path = raw.get("video_path", data.video_path)
    data.framerate = int(raw.get("framerate", data.framerate))
    res = raw.get("resolution")
    if isinstance(res, (list, tuple)) and len(res) == 2:
        data.width, data.height = int(res[0]), int(res[1])
    elif isinstance(res, str) and "x" in res.lower():
        w, h = res.lower().split("x", 1)
        data.width, data.height = int(w.strip()), int(h.strip())
    data.intro = raw.get("intro", "").strip()

    for b in raw.get("beats", []):
        if "time" not in b or "text" not in b:
            continue
        data.beats.append(
            Beat(
                time_sec=parse_timecode(str(b["time"])),
                text=str(b["text"]).strip(),
                label=str(b.get("label", "")).strip(),
            )
        )
    return data


def parse_csv(path: Path) -> ReviewData:
    data = ReviewData()
    with path.open(encoding="utf-8-sig", newline="") as f:
        # Allow optional metadata lines starting with '#'
        lines: list[str] = []
        for ln in f:
            if ln.strip().startswith("#"):
                m = META_LINE_RE.match(ln.strip().lstrip("#").strip())
                if m:
                    key = m.group("key").strip().lower()
                    val = m.group("value").strip()
                    if key in ("제목", "title"):
                        data.title = val
                    elif key in ("영상", "video", "video_path"):
                        data.video_path = val
                    elif key in ("프레임레이트", "framerate", "fps"):
                        data.framerate = int(val)
                    elif key in ("해상도", "resolution") and "x" in val.lower():
                        w, h = val.lower().split("x", 1)
                        data.width, data.height = int(w.strip()), int(h.strip())
                continue
            lines.append(ln)

        reader = csv.DictReader(lines)
        for row in reader:
            time_val = (row.get("time") or row.get("타임") or "").strip()
            text_val = (row.get("text") or row.get("대사") or "").strip()
            label_val = (row.get("label") or row.get("라벨") or "").strip()
            if not time_val or not text_val:
                continue
            try:
                t = parse_timecode(time_val)
            except ValueError:
                continue
            data.beats.append(Beat(time_sec=t, text=text_val, label=label_val))

    return data


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    return "text"


# --------------------------------------------------------------------------- #
# Generators
# --------------------------------------------------------------------------- #

def build_xml(data: ReviewData, sequence_duration_frames: int | None = None) -> str:
    fps = data.framerate
    if sequence_duration_frames is None:
        max_sec = max((b.time_sec for b in data.beats), default=600)
        sequence_duration_frames = int(max(max_sec * 2, 3600) * fps)

    file_url_path = data.video_path.replace("\\", "/")
    if file_url_path and not file_url_path.startswith("file://"):
        # Windows absolute path: file://localhost/C:/...
        if re.match(r"^[A-Za-z]:/", file_url_path):
            file_url = f"file://localhost/{file_url_path}"
        else:
            file_url = f"file://{file_url_path}"
    else:
        file_url = file_url_path

    title_xml = xml_escape(data.title)
    file_url_xml = xml_escape(file_url)
    filename = Path(data.video_path).name if data.video_path else "source.mp4"
    filename_xml = xml_escape(filename)

    markers_xml: list[str] = []
    for idx, beat in enumerate(data.beats, 1):
        frame = int(round(beat.time_sec * fps))
        label = beat.label or f"비트 {idx}"
        comment = beat.text[:120]
        markers_xml.append(
            "\t\t<marker>\n"
            f"\t\t\t<comment>{xml_escape(comment)}</comment>\n"
            f"\t\t\t<name>{xml_escape(f'{idx}. {label}')}</name>\n"
            f"\t\t\t<in>{frame}</in>\n"
            f"\t\t\t<out>{frame}</out>\n"
            "\t\t</marker>"
        )
    markers_block = "\n".join(markers_xml) if markers_xml else ""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
\t<sequence id="sequence-1">
\t\t<uuid>review-to-pp-{abs(hash(data.title)) % 1_000_000}</uuid>
\t\t<duration>{sequence_duration_frames}</duration>
\t\t<rate>
\t\t\t<timebase>{fps}</timebase>
\t\t\t<ntsc>FALSE</ntsc>
\t\t</rate>
\t\t<name>{title_xml}</name>
\t\t<media>
\t\t\t<video>
\t\t\t\t<format>
\t\t\t\t\t<samplecharacteristics>
\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t<timebase>{fps}</timebase>
\t\t\t\t\t\t\t<ntsc>FALSE</ntsc>
\t\t\t\t\t\t</rate>
\t\t\t\t\t\t<width>{data.width}</width>
\t\t\t\t\t\t<height>{data.height}</height>
\t\t\t\t\t\t<anamorphic>FALSE</anamorphic>
\t\t\t\t\t\t<pixelaspectratio>square</pixelaspectratio>
\t\t\t\t\t\t<fielddominance>none</fielddominance>
\t\t\t\t\t\t<colordepth>24</colordepth>
\t\t\t\t\t</samplecharacteristics>
\t\t\t\t</format>
\t\t\t\t<track>
\t\t\t\t\t<enabled>TRUE</enabled>
\t\t\t\t\t<locked>FALSE</locked>
\t\t\t\t\t<clipitem id="clipitem-1">
\t\t\t\t\t\t<masterclipid>masterclip-1</masterclipid>
\t\t\t\t\t\t<name>{filename_xml}</name>
\t\t\t\t\t\t<enabled>TRUE</enabled>
\t\t\t\t\t\t<duration>{sequence_duration_frames}</duration>
\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t<timebase>{fps}</timebase>
\t\t\t\t\t\t\t<ntsc>FALSE</ntsc>
\t\t\t\t\t\t</rate>
\t\t\t\t\t\t<start>0</start>
\t\t\t\t\t\t<end>{sequence_duration_frames}</end>
\t\t\t\t\t\t<in>0</in>
\t\t\t\t\t\t<out>{sequence_duration_frames}</out>
\t\t\t\t\t\t<file id="file-1">
\t\t\t\t\t\t\t<name>{filename_xml}</name>
\t\t\t\t\t\t\t<pathurl>{file_url_xml}</pathurl>
\t\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t\t<timebase>{fps}</timebase>
\t\t\t\t\t\t\t\t<ntsc>FALSE</ntsc>
\t\t\t\t\t\t\t</rate>
\t\t\t\t\t\t\t<duration>{sequence_duration_frames}</duration>
\t\t\t\t\t\t\t<media>
\t\t\t\t\t\t\t\t<video>
\t\t\t\t\t\t\t\t\t<samplecharacteristics>
\t\t\t\t\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t\t\t\t\t<timebase>{fps}</timebase>
\t\t\t\t\t\t\t\t\t\t\t<ntsc>FALSE</ntsc>
\t\t\t\t\t\t\t\t\t\t</rate>
\t\t\t\t\t\t\t\t\t\t<width>{data.width}</width>
\t\t\t\t\t\t\t\t\t\t<height>{data.height}</height>
\t\t\t\t\t\t\t\t\t\t<anamorphic>FALSE</anamorphic>
\t\t\t\t\t\t\t\t\t\t<pixelaspectratio>square</pixelaspectratio>
\t\t\t\t\t\t\t\t\t\t<fielddominance>none</fielddominance>
\t\t\t\t\t\t\t\t\t</samplecharacteristics>
\t\t\t\t\t\t\t\t</video>
\t\t\t\t\t\t\t\t<audio>
\t\t\t\t\t\t\t\t\t<samplecharacteristics>
\t\t\t\t\t\t\t\t\t\t<depth>16</depth>
\t\t\t\t\t\t\t\t\t\t<samplerate>48000</samplerate>
\t\t\t\t\t\t\t\t\t</samplecharacteristics>
\t\t\t\t\t\t\t\t\t<channelcount>2</channelcount>
\t\t\t\t\t\t\t\t</audio>
\t\t\t\t\t\t\t</media>
\t\t\t\t\t\t</file>
\t\t\t\t\t</clipitem>
\t\t\t\t</track>
\t\t\t</video>
\t\t\t<audio>
\t\t\t\t<track>
\t\t\t\t\t<enabled>TRUE</enabled>
\t\t\t\t\t<locked>FALSE</locked>
\t\t\t\t\t<clipitem id="clipitem-2">
\t\t\t\t\t\t<masterclipid>masterclip-1</masterclipid>
\t\t\t\t\t\t<name>{filename_xml}</name>
\t\t\t\t\t\t<enabled>TRUE</enabled>
\t\t\t\t\t\t<duration>{sequence_duration_frames}</duration>
\t\t\t\t\t\t<rate>
\t\t\t\t\t\t\t<timebase>{fps}</timebase>
\t\t\t\t\t\t\t<ntsc>FALSE</ntsc>
\t\t\t\t\t\t</rate>
\t\t\t\t\t\t<start>0</start>
\t\t\t\t\t\t<end>{sequence_duration_frames}</end>
\t\t\t\t\t\t<in>0</in>
\t\t\t\t\t\t<out>{sequence_duration_frames}</out>
\t\t\t\t\t\t<file id="file-1"/>
\t\t\t\t\t\t<sourcetrack>
\t\t\t\t\t\t\t<mediatype>audio</mediatype>
\t\t\t\t\t\t\t<trackindex>1</trackindex>
\t\t\t\t\t\t</sourcetrack>
\t\t\t\t\t</clipitem>
\t\t\t\t</track>
\t\t\t</audio>
\t\t</media>
{markers_block}
\t</sequence>
</xmeml>
"""


def build_srt(data: ReviewData) -> str:
    """Build SRT for narration. Intro starts at 0:00, then each beat follows sequentially."""
    cues: list[tuple[float, float, str]] = []
    cursor = 0.0

    if data.intro:
        dur = estimate_duration(data.intro)
        cues.append((cursor, cursor + dur, data.intro))
        cursor += dur

    for beat in data.beats:
        dur = estimate_duration(beat.text)
        cues.append((cursor, cursor + dur, beat.text))
        cursor += dur

    lines: list[str] = []
    for i, (start, end, text) in enumerate(cues, 1):
        wrapped = "\n".join(split_text_chunks(text))
        lines.append(str(i))
        lines.append(f"{format_srt_time(start)} --> {format_srt_time(end)}")
        lines.append(wrapped)
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def convert(
    input_path: Path,
    output_dir: Path | None = None,
    override_video: str | None = None,
    override_title: str | None = None,
) -> tuple[Path, Path]:
    fmt = detect_format(input_path)
    if fmt == "json":
        data = parse_json(input_path)
    elif fmt == "csv":
        data = parse_csv(input_path)
    else:
        data = parse_text(input_path)

    if override_video:
        data.video_path = override_video
    if override_title:
        data.title = override_title

    if not data.beats:
        raise ValueError("No timestamped beats found in input. Add at least one (MM:SS) or (HH:MM:SS) marker.")

    out_dir = output_dir or input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    base = input_path.stem

    xml_path = out_dir / f"{base}_markers.xml"
    srt_path = out_dir / f"{base}_narration.srt"

    xml_path.write_text(build_xml(data), encoding="utf-8")
    srt_path.write_text(build_srt(data), encoding="utf-8")

    return xml_path, srt_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="review_to_pp",
        description="Convert a review script (.txt/.json/.csv) into Premiere Pro XML + SRT subtitle.",
    )
    parser.add_argument("input", type=Path, help="Input review script (.txt, .json, or .csv)")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output directory (default: input file's folder)")
    parser.add_argument("--video", type=str, default=None, help="Override video path declared in input")
    parser.add_argument("--title", type=str, default=None, help="Override title declared in input")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"[ERROR] Input file not found: {args.input}", file=sys.stderr)
        return 1

    try:
        xml_path, srt_path = convert(args.input, args.output, args.video, args.title)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    print(f"[OK] XML : {xml_path}")
    print(f"[OK] SRT : {srt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
