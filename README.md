# video_transcriber

영상에서 음성을 추출해 **자막(SRT)** 을 생성하는 도구. faster-whisper 기반, 다국어 자동 감지, PyQt6 GUI 제공.

## 설치

```
pip install -r requirements.txt
```

설치 용량 안내:
- faster-whisper / ctranslate2 / tokenizers: 약 500MB
- PyQt6: 약 60MB
- 첫 실행 시 Whisper 모델은 별도로 자동 다운로드 (`large-v3` 기준 ~3GB)

## 사용법

### 1) GUI (권장)

```
python gui.py
```

- **Browse…** 로 영상/오디오 파일 선택 (`.mp4 .mkv .avi .mov .webm .mp3 .wav .m4a` 등)
- **Model** 에서 정확도/속도 균형 선택:
  - `tiny` / `base` : 빠름, 정확도 낮음
  - `small` / `medium` : 균형
  - `large-v3` : 가장 정확함 (권장)
- **Language** 는 `auto-detect` 가 기본. 특정 언어로 강제하려면 선택
- **Output** 에서 `.srt` / `.txt` / `.timestamped.txt` 중 원하는 만큼 체크
- **Generate subtitles** 클릭. 진행률 바와 로그가 실시간 표시됨
- 완료 후 **Open output folder** 로 결과 폴더 열기

### 2) CLI

```
python transcribe.py "C:\path\to\video.mp4"
```

자주 쓰는 옵션:

```
python transcribe.py video.mp4 --model large-v3 --language ko --format srt,txt
python transcribe.py podcast.mp3 --model medium --format srt --output-dir D:\subs
python transcribe.py video.mp4 --force
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--model` | `tiny`, `base`, `small`, `medium`, `large-v3` | `large-v3` |
| `--language` | `ko`, `en`, `ja`, `zh` 등 ISO 코드. 생략 시 자동 감지 | 자동 감지 |
| `--format` | `srt`, `txt`, `timestamped` (콤마 구분) | `srt` |
| `--output-dir` | 출력 폴더 | `./output` |
| `--force` | 기존 결과가 있어도 다시 생성 | off |

## 출력 형식

- `videoname.srt` : 표준 자막 파일 (`HH:MM:SS,ms --> HH:MM:SS,ms`)
- `videoname.txt` : 타임스탬프 없는 순수 텍스트
- `videoname.timestamped.txt` : `[mm:ss]` 타임스탬프 포함 텍스트

## 소요 시간 (참고)

| 모델 | 1시간 영상 (CPU) | 1시간 영상 (GPU/CUDA) |
|------|----------------|----------------------|
| tiny | ~2분 | ~30초 |
| base | ~4분 | ~1분 |
| small | ~8분 | ~1.5분 |
| medium | ~15분 | ~2분 |
| large-v3 | ~25분 | ~3분 |

## ffmpeg

별도 설치 불필요. `imageio-ffmpeg` 가 ffmpeg 바이너리를 포함합니다.

## 회사망 SSL 문제

기본적으로 SSL 인증서 검증을 비활성화해 MITM 프록시 환경에서도 모델 다운로드가 됩니다.

SSL 검증을 활성화하려면:

```
set VERIFY_SSL=1
python gui.py
```

## 시스템 요구사항

- Python 3.10+ (3.12 권장, Windows에서 검증)
- RAM: CPU 모드 약 3GB 이상 권장 (large-v3는 5GB+ 권장)
- GPU 모드: CUDA 지원 NVIDIA GPU + 4GB+ VRAM
