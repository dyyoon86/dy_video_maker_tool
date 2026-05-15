import sys
import os
import ssl
import subprocess
import argparse
import time
import tempfile
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass
try:
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

if os.environ.get("VERIFY_SSL", "0") != "1":
    ssl._create_default_https_context = ssl._create_unverified_context
    os.environ.setdefault("CURL_CA_BUNDLE", "")
    os.environ.setdefault("REQUESTS_CA_BUNDLE", "")


LogFn = Callable[[str], None]
ProgressFn = Callable[[float], None]


def _default_log(msg: str) -> None:
    print(msg)


def _default_progress(_pct: float) -> None:
    pass


def extract_audio(media_path: str, wav_path: str, log: LogFn = _default_log) -> None:
    try:
        import imageio_ffmpeg
    except ImportError:
        raise RuntimeError("imageio-ffmpeg is not installed. Run: pip install imageio-ffmpeg")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    log(f"[INFO] FFmpeg: {ffmpeg}")
    log(f"[INFO] Extracting audio from: {media_path}")

    result = subprocess.run(
        [
            ffmpeg, "-y", "-i", media_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            wav_path,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr}")

    log("[INFO] Audio extraction complete.")


def load_model(model_size: str = "large-v3", log: LogFn = _default_log):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("faster-whisper is not installed. Run: pip install faster-whisper")

    log(f"[INFO] Loading Whisper {model_size} model (first run downloads model files)...")
    load_start = time.time()

    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
        device_used = "GPU (float16)"
    except Exception as e:
        log(f"[INFO] GPU unavailable ({e}), falling back to CPU (int8).")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        device_used = "CPU (int8)"

    elapsed = time.time() - load_start
    log(f"[INFO] Model loaded on {device_used} in {elapsed:.1f}s")
    return model, device_used


def format_time_short(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def format_time_srt(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: List[Dict[str, Any]], out_path: Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(segments, start=1):
            start = format_time_srt(seg["start"])
            end = format_time_srt(seg["end"])
            text = seg["text"].strip()
            if not text:
                continue
            f.write(f"{idx}\n{start} --> {end}\n{text}\n\n")


def write_plain_txt(segments: List[Dict[str, Any]], out_path: Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(s["text"].strip() for s in segments if s["text"].strip()))
        f.write("\n")


def write_timestamped_txt(segments: List[Dict[str, Any]], out_path: Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        for s in segments:
            text = s["text"].strip()
            if not text:
                continue
            f.write(f"[{format_time_short(s['start'])}] {text}\n")


def transcribe(
    media_path: str,
    model_size: str = "large-v3",
    language: Optional[str] = None,
    output_formats: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    force: bool = False,
    log: LogFn = _default_log,
    progress: ProgressFn = _default_progress,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """
    output_formats: subset of ['srt', 'txt', 'timestamped']. Defaults to ['srt'].
    language: None = auto-detect, or ISO code like 'ko', 'en', 'ja', 'zh'.
    cancel_check: optional callable returning True if user requested cancel.
    """
    if output_formats is None:
        output_formats = ["srt"]

    media_path = os.path.abspath(media_path)
    if not os.path.isfile(media_path):
        raise FileNotFoundError(f"File not found: {media_path}")

    video_name = Path(media_path).stem
    out_dir = Path(output_dir) if output_dir else Path(__file__).parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_paths = {
        "srt": out_dir / f"{video_name}.srt",
        "txt": out_dir / f"{video_name}.txt",
        "timestamped": out_dir / f"{video_name}.timestamped.txt",
    }
    targets = [out_paths[fmt] for fmt in output_formats]

    if not force and all(p.exists() for p in targets):
        log(f"[INFO] Output already exists. Use --force to re-transcribe.")
        for p in targets:
            log(f"  -> {p}")
        return {"skipped": True, "outputs": [str(p) for p in targets]}

    total_start = time.time()
    progress(0.0)

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, f"{video_name}.wav")

        extract_audio(media_path, wav_path, log=log)
        progress(0.10)
        if cancel_check and cancel_check():
            log("[INFO] Cancelled by user.")
            return {"cancelled": True}

        model, device_used = load_model(model_size=model_size, log=log)
        progress(0.20)
        if cancel_check and cancel_check():
            log("[INFO] Cancelled by user.")
            return {"cancelled": True}

        lang_label = language if language else "auto-detect"
        log(f"[INFO] Transcribing (language={lang_label}, beam_size=5, vad_filter=on)...")
        transcribe_start = time.time()

        segments_iter, info = model.transcribe(
            wav_path,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        detected_lang = info.language
        duration = info.duration or 0.0
        log(f"[INFO] Detected language: {detected_lang} (probability {info.language_probability:.2f})")
        log(f"[INFO] Audio duration: {duration:.1f}s")

        collected: List[Dict[str, Any]] = []
        for segment in segments_iter:
            if cancel_check and cancel_check():
                log("[INFO] Cancelled by user.")
                return {"cancelled": True, "partial": collected}

            text = segment.text.strip()
            if not text:
                continue

            collected.append({
                "start": segment.start,
                "end": segment.end,
                "text": text,
            })

            log(f"[{format_time_short(segment.start)}] {text}")

            if duration > 0:
                pct = 0.20 + 0.78 * min(segment.end / duration, 1.0)
                progress(min(pct, 0.98))

        transcribe_elapsed = time.time() - transcribe_start

    written: List[str] = []
    if "srt" in output_formats:
        write_srt(collected, out_paths["srt"])
        written.append(str(out_paths["srt"]))
    if "txt" in output_formats:
        write_plain_txt(collected, out_paths["txt"])
        written.append(str(out_paths["txt"]))
    if "timestamped" in output_formats:
        write_timestamped_txt(collected, out_paths["timestamped"])
        written.append(str(out_paths["timestamped"]))

    progress(1.0)
    total_elapsed = time.time() - total_start

    log("")
    log(f"[DONE] Transcription complete.")
    log(f"  Device         : {device_used}")
    log(f"  Detected lang  : {detected_lang}")
    log(f"  Transcribe time: {transcribe_elapsed:.1f}s")
    log(f"  Total time     : {total_elapsed:.1f}s")
    for w in written:
        log(f"  -> {w}")

    return {
        "skipped": False,
        "cancelled": False,
        "outputs": written,
        "language": detected_lang,
        "duration": duration,
        "device": device_used,
        "elapsed": total_elapsed,
        "output_dir": str(out_dir),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Video/Audio to subtitle (SRT) transcription using faster-whisper"
    )
    parser.add_argument("media", help="Path to the video or audio file")
    parser.add_argument("--model", default="large-v3",
                        choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="Whisper model size (default: large-v3)")
    parser.add_argument("--language", default=None,
                        help="Language code (e.g. ko, en, ja, zh). Omit for auto-detect.")
    parser.add_argument("--format", default="srt",
                        help="Output formats, comma-separated. Choices: srt,txt,timestamped (default: srt)")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (default: ./output next to this script)")
    parser.add_argument("--force", action="store_true",
                        help="Re-transcribe even if output already exists")
    args = parser.parse_args()

    formats = [f.strip() for f in args.format.split(",") if f.strip()]
    valid = {"srt", "txt", "timestamped"}
    bad = [f for f in formats if f not in valid]
    if bad:
        print(f"[ERROR] Invalid format(s): {bad}. Choose from {sorted(valid)}.")
        sys.exit(1)

    try:
        transcribe(
            args.media,
            model_size=args.model,
            language=args.language,
            output_formats=formats,
            output_dir=args.output_dir,
            force=args.force,
        )
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
