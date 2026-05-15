"""
SRT subtitle translator via Google Translate (free, no API key).

Usage:
  python translate_srt.py "C:\\path\\to\\video.srt"
  python translate_srt.py video.srt --source ja --target ko
  python translate_srt.py video.srt --engine deepl --target en
"""
import sys
import os
import ssl
import time
import argparse
from pathlib import Path

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


ENGINES = {
    "google": "GoogleTranslator",
    "mymemory": "MyMemoryTranslator",
    "deepl": "DeeplTranslator",
    "libre": "LibreTranslator",
    "papago": "PapagoTranslator",
}


def build_translator(engine: str, source: str, target: str):
    import deep_translator as dt

    if engine == "google":
        return dt.GoogleTranslator(source=source, target=target)
    if engine == "mymemory":
        return dt.MyMemoryTranslator(source=source, target=target)
    if engine == "deepl":
        api_key = os.environ.get("DEEPL_API_KEY")
        if not api_key:
            raise RuntimeError("DeepL needs DEEPL_API_KEY env var. Get free key at https://www.deepl.com/pro-api")
        return dt.DeeplTranslator(api_key=api_key, source=source, target=target)
    if engine == "libre":
        return dt.LibreTranslator(source=source, target=target)
    if engine == "papago":
        client_id = os.environ.get("PAPAGO_CLIENT_ID")
        secret = os.environ.get("PAPAGO_CLIENT_SECRET")
        if not (client_id and secret):
            raise RuntimeError("Papago needs PAPAGO_CLIENT_ID and PAPAGO_CLIENT_SECRET env vars.")
        return dt.PapagoTranslator(client_id=client_id, secret_key=secret, source=source, target=target)
    raise ValueError(f"Unknown engine: {engine}")


def translate_srt(
    src_path: str,
    source: str = "ja",
    target: str = "ko",
    engine: str = "google",
    force: bool = False,
    batch_save: int = 100,
    sleep_every: int = 0,
    sleep_seconds: float = 0.0,
) -> None:
    try:
        import srt
        from tqdm import tqdm
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}")
        print("        Run: pip install deep-translator srt tqdm")
        sys.exit(1)

    src = Path(src_path).resolve()
    if not src.is_file():
        print(f"[ERROR] File not found: {src}")
        sys.exit(1)

    out = src.with_name(f"{src.stem}_{target}.srt")
    if out.exists() and not force:
        print(f"[INFO] Output already exists: {out}")
        print(f"[INFO] Use --force to overwrite.")
        return

    print(f"[INFO] Source : {src}")
    print(f"[INFO] Engine : {engine}  ({source} -> {target})")
    print(f"[INFO] Output : {out}")

    raw = src.read_text(encoding="utf-8-sig")
    subs = list(srt.parse(raw))
    total = len(subs)
    if total == 0:
        print("[ERROR] No subtitle blocks parsed. Is this a valid SRT?")
        sys.exit(1)
    print(f"[INFO] Parsed {total} subtitle blocks.")

    try:
        translator = build_translator(engine, source, target)
    except Exception as e:
        print(f"[ERROR] Failed to init translator: {e}")
        sys.exit(1)

    cache: dict[str, str] = {}
    hits = 0
    fails = 0
    failed_indices: list[int] = []

    start = time.time()

    for i, s in enumerate(tqdm(subs, unit="block", ncols=80)):
        original = s.content.strip()
        if not original:
            continue

        if original in cache:
            s.content = cache[original]
            hits += 1
            continue

        translated = None
        for attempt in range(3):
            try:
                translated = translator.translate(original)
                if translated:
                    break
            except Exception as e:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                tqdm.write(f"[WARN] Block #{i + 1} failed after 3 retries: {e}")
                fails += 1
                failed_indices.append(i + 1)

        if translated:
            s.content = translated
            cache[original] = translated

        if batch_save > 0 and (i + 1) % batch_save == 0:
            out.write_text(srt.compose(subs), encoding="utf-8")

        if sleep_every > 0 and (i + 1) % sleep_every == 0 and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    out.write_text(srt.compose(subs), encoding="utf-8")

    elapsed = time.time() - start
    print("")
    print(f"[DONE] Translation finished.")
    print(f"  Total blocks : {total}")
    print(f"  Cache hits   : {hits}  ({hits / total * 100:.1f}%)")
    print(f"  Failed       : {fails}")
    if failed_indices:
        shown = failed_indices[:20]
        more = "..." if len(failed_indices) > 20 else ""
        print(f"  Failed idx   : {shown}{more}")
    print(f"  Elapsed      : {elapsed:.1f}s ({elapsed / max(total, 1):.2f}s/block avg)")
    print(f"  Output       : {out}")


def main():
    parser = argparse.ArgumentParser(
        description="SRT subtitle translator using free online translators (no API key for Google).",
    )
    parser.add_argument("srt", help="Path to source SRT file")
    parser.add_argument("--source", "-s", default="ja", help="Source language code (default: ja)")
    parser.add_argument("--target", "-t", default="ko", help="Target language code (default: ko)")
    parser.add_argument(
        "--engine", "-e", default="google",
        choices=list(ENGINES.keys()),
        help="Translation engine (default: google)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing output file")
    parser.add_argument(
        "--batch-save", type=int, default=100,
        help="Save partial result every N blocks (default: 100, 0=disable)",
    )
    parser.add_argument(
        "--sleep-every", type=int, default=0,
        help="Pause after every N blocks to avoid rate-limiting (default: 0=off)",
    )
    parser.add_argument(
        "--sleep-seconds", type=float, default=0.0,
        help="Pause duration in seconds when --sleep-every triggers (default: 0)",
    )
    args = parser.parse_args()

    translate_srt(
        args.srt,
        source=args.source,
        target=args.target,
        engine=args.engine,
        force=args.force,
        batch_save=args.batch_save,
        sleep_every=args.sleep_every,
        sleep_seconds=args.sleep_seconds,
    )


if __name__ == "__main__":
    main()
