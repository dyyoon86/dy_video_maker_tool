"""
SRT translator using DeepL official API.

CLI:
  python deepl_translate_srt.py "C:\\path\\to\\video.srt"
  python deepl_translate_srt.py video.srt --source JA --target KO
  python deepl_translate_srt.py --usage
  python deepl_translate_srt.py --save-key "your-deepl-key:fx"

Library (used by deepl_gui.py):
  translate_srt(..., log=..., progress=..., cancel_check=...)

Auth precedence:
  1) --api-key CLI arg / api_key kwarg
  2) DEEPL_API_KEY env var
  3) .deepl_key file next to this script
"""
import os
import sys
import ssl
import argparse
from pathlib import Path
from typing import Optional, Callable, Any

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


DEFAULT_KEY_FILE = Path(__file__).parent / ".deepl_key"

LogFn = Callable[[str], None]
ProgressFn = Callable[[float], None]
CancelFn = Callable[[], bool]


def _default_log(msg: str) -> None:
    print(msg)


def _default_progress(_pct: float) -> None:
    pass


def _default_cancel() -> bool:
    return False


def load_api_key(cli_key: Optional[str]) -> str:
    if cli_key:
        return cli_key.strip()
    env = os.environ.get("DEEPL_API_KEY", "").strip()
    if env:
        return env
    if DEFAULT_KEY_FILE.exists():
        key = DEFAULT_KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    raise RuntimeError(
        "DeepL API key not found. Save it via --save-key, set DEEPL_API_KEY env var, "
        "or pass --api-key."
    )


def save_api_key(key: str) -> None:
    DEFAULT_KEY_FILE.write_text(key.strip(), encoding="utf-8")
    try:
        os.chmod(DEFAULT_KEY_FILE, 0o600)
    except OSError:
        pass


def get_usage(api_key: str) -> dict[str, Any]:
    import deepl
    translator = deepl.Translator(api_key)
    usage = translator.get_usage()
    if usage.character.valid:
        return {
            "valid": True,
            "count": usage.character.count,
            "limit": usage.character.limit,
            "remaining": usage.character.limit - usage.character.count,
        }
    return {"valid": False}


def translate_srt(
    input_path: str,
    source: Optional[str] = "JA",
    target: str = "KO",
    api_key: Optional[str] = None,
    force: bool = False,
    batch_size: int = 50,
    output_path: Optional[str] = None,
    log: LogFn = _default_log,
    progress: ProgressFn = _default_progress,
    cancel_check: CancelFn = _default_cancel,
) -> dict[str, Any]:
    """
    Translate a single SRT file via DeepL.
    Returns a dict with status info. Raises on fatal errors.
    """
    try:
        import deepl
        import srt
    except ImportError as e:
        raise RuntimeError(f"Missing dependency: {e}. Run: pip install deepl srt")

    src = Path(input_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"File not found: {src}")

    if output_path:
        out = Path(output_path).resolve()
    else:
        suffix = target.lower().replace("-", "_")
        out = src.with_name(f"{src.stem}_{suffix}.srt")

    if out.exists() and not force:
        log(f"[INFO] Output already exists: {out}")
        log(f"[INFO] Enable 'force overwrite' to re-translate.")
        return {"skipped": True, "output": str(out)}

    key = api_key or load_api_key(None)
    translator = deepl.Translator(key)

    usage_before = None
    try:
        u = translator.get_usage()
        if u.character.valid:
            usage_before = (u.character.count, u.character.limit)
            log(f"[INFO] DeepL usage before: {u.character.count:,}/{u.character.limit:,}")
    except Exception as e:
        log(f"[WARN] Could not fetch usage: {e}")

    raw = src.read_text(encoding="utf-8-sig")
    subs = list(srt.parse(raw))
    total = len(subs)
    if total == 0:
        raise ValueError("No subtitle blocks found. Invalid SRT?")

    log(f"[INFO] Source : {src}")
    log(f"[INFO] Output : {out}")
    src_label = source if source else "auto-detect"
    log(f"[INFO] Parsed {total} blocks. Translating {src_label} -> {target} via DeepL...")

    progress(0.02)

    unique_texts: list[str] = []
    seen: dict[str, None] = {}
    for s in subs:
        text = s.content.strip()
        if text and text not in seen:
            seen[text] = None
            unique_texts.append(text)

    unique_count = len(unique_texts)
    saved_pct = (1 - unique_count / total) * 100 if total else 0
    log(f"[INFO] Unique texts: {unique_count} / {total}  (deduplication saves {saved_pct:.1f}%)")

    progress(0.05)

    cache: dict[str, str] = {}
    failed = 0
    batches = max(1, (unique_count + batch_size - 1) // batch_size)

    for bi in range(batches):
        if cancel_check():
            log("[INFO] Cancelled by user.")
            return {"cancelled": True}

        batch_start = bi * batch_size
        batch = unique_texts[batch_start:batch_start + batch_size]
        try:
            results = translator.translate_text(
                batch,
                source_lang=source if source else None,
                target_lang=target,
                preserve_formatting=True,
            )
            if not isinstance(results, list):
                results = [results]
            for original, result in zip(batch, results):
                cache[original] = result.text
        except Exception as e:
            log(f"[WARN] Batch {bi + 1}/{batches} failed: {e}")
            for original in batch:
                cache[original] = original
                failed += 1

        pct = 0.05 + 0.90 * ((bi + 1) / batches)
        progress(min(pct, 0.95))
        log(f"[INFO] Batch {bi + 1}/{batches} done.")

    for s in subs:
        text = s.content.strip()
        if text in cache:
            s.content = cache[text]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(srt.compose(subs), encoding="utf-8")

    progress(1.0)
    log("")
    log(f"[DONE] Translation complete.")
    log(f"  Total blocks : {total}")
    log(f"  Unique       : {unique_count}")
    log(f"  Failed       : {failed}")
    log(f"  Output       : {out}")

    usage_after = None
    try:
        u = translator.get_usage()
        if u.character.valid:
            usage_after = (u.character.count, u.character.limit)
            log(f"  Usage after  : {u.character.count:,}/{u.character.limit:,}")
    except Exception:
        pass

    return {
        "skipped": False,
        "cancelled": False,
        "output": str(out),
        "total": total,
        "unique": unique_count,
        "failed": failed,
        "usage_before": usage_before,
        "usage_after": usage_after,
    }


def main():
    parser = argparse.ArgumentParser(
        description="DeepL-based SRT translator (official SDK).",
    )
    parser.add_argument("srt", nargs="?", help="Path to source SRT file")
    parser.add_argument("--api-key", help="DeepL API key")
    parser.add_argument("--save-key", metavar="KEY",
                        help="Save the given DeepL API key to .deepl_key and exit")
    parser.add_argument("--source", default="JA",
                        help="Source language code (default: JA). Use 'AUTO' for auto-detect.")
    parser.add_argument("--target", default="KO",
                        help="Target language code (default: KO).")
    parser.add_argument("--output", "-o", help="Output SRT path")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Texts per API call (default: 50)")
    parser.add_argument("--usage", action="store_true",
                        help="Show DeepL API usage and exit")
    args = parser.parse_args()

    if args.save_key:
        save_api_key(args.save_key)
        print(f"[INFO] API key saved to: {DEFAULT_KEY_FILE}")
        if not args.srt:
            return

    if args.usage:
        try:
            key = load_api_key(args.api_key)
        except RuntimeError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)
        info = get_usage(key)
        if info["valid"]:
            print(f"Characters: {info['count']:,} / {info['limit']:,}")
            print(f"Remaining : {info['remaining']:,}")
        else:
            print("Character usage not available.")
        return

    if not args.srt:
        parser.error("the following argument is required: srt")

    source = None if args.source.upper() == "AUTO" else args.source.upper()

    # tqdm-style progress for CLI
    try:
        from tqdm import tqdm
        bar = tqdm(total=100, desc="Progress", ncols=80, bar_format="{l_bar}{bar}| {n_fmt}%")
        last = [0]

        def cli_progress(pct: float) -> None:
            cur = int(pct * 100)
            if cur > last[0]:
                bar.update(cur - last[0])
                last[0] = cur

        def cli_log(msg: str) -> None:
            tqdm.write(msg)
    except ImportError:
        bar = None
        cli_progress = _default_progress
        cli_log = print

    try:
        translate_srt(
            args.srt,
            source=source,
            target=args.target,
            api_key=args.api_key,
            force=args.force,
            batch_size=args.batch_size,
            output_path=args.output,
            log=cli_log,
            progress=cli_progress,
        )
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
    finally:
        if bar is not None:
            bar.close()


if __name__ == "__main__":
    main()
