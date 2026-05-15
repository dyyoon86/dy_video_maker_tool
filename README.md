# video_maker_tool

영상 콘텐츠 제작 전 과정을 지원하는 통합 툴킷. 자막 추출 → 번역 → 편집 자동화까지 한 워크스페이스에서 처리.

## 📦 구성

| 도구 | 위치 | 용도 |
| :--- | :--- | :--- |
| **transcriber** | [`transcriber/`](./transcriber/) | 영상에서 음성 → 자막(SRT/TXT) 추출. faster-whisper 기반, PyQt6 GUI |
| **translator** | [`translator/`](./translator/) | SRT 자막 → 다른 언어로 번역. DeepL API 기반, PyQt6 GUI + 드래그&드롭 |
| **review_to_pp** | [`review_to_pp/`](./review_to_pp/) | 리뷰 스크립트(.txt/.json/.csv) → Premiere Pro XML + SRT 자동 생성 |

### 표준 워크플로우

```
[원본 영상]
   ↓ transcriber (음성 → 자막 추출)
[자막 .srt]
   ↓ translator (다국어 번역, 선택)
[번역된 자막]
   ↓ (리뷰 스크립트 작성)
[리뷰 스크립트 .txt]
   ↓ review_to_pp (Premiere XML + 자막 SRT 생성)
[Premiere Pro 임포트] → 편집 → 완성
```

## 🚀 설치

각 도구는 독립적으로 동작합니다. 도구별 디렉토리에서 설치하거나, 한 번에 전부:

```powershell
pip install -r requirements.txt
```

> Python 3.10+ 필요 (3.12 권장, Windows 검증). 자세한 사용법은 각 도구의 `README.md` 또는 본 README 의 도구별 섹션 참고.

## 📋 각 도구 빠른 안내

### 🎙️ transcriber — 음성 → 자막

영상/오디오에서 음성을 추출해 SRT 자막을 생성. faster-whisper 다국어 자동 감지.

```powershell
# CLI
python transcriber/transcribe.py "C:\path\to\video.mp4" --model large-v3

# GUI
python transcriber/transcribe_gui.py
```

자세한 옵션: [`transcriber/`](./transcriber/) 디렉토리 참고. 모델 선택, 출력 형식, GPU/CPU 설정, ffmpeg 내장 등.

### 🌐 translator — SRT 번역

DeepL API 로 SRT 자막을 한국어/영어 등으로 번역.

```powershell
# CLI
python translator/deepl_translate_srt.py input.ja.srt --target KO

# GUI (드래그&드롭)
translator\deepl_gui.bat

# 드래그&드롭 직접 변환 (가장 빠름)
# → .srt 파일을 translator\translate_drop.bat 에 끌어다 놓기
```

DeepL API 키 설정:
- 환경변수 `DEEPL_API_KEY`, 또는
- `translator/.deepl_key` 파일에 키 한 줄로 저장, 또는
- `--set-key <KEY>` 옵션으로 일회 등록

### ✂️ review_to_pp — 리뷰 스크립트 → Premiere

타임스탬프가 박힌 리뷰 스크립트(.txt/.json/.csv)를 받아 **Premiere Pro 임포트용 XML** 과 **내레이션 SRT** 를 한 번에 생성.

```powershell
# CLI
python review_to_pp/review_to_pp.py review.txt

# GUI (드래그&드롭, 일괄 변환)
review_to_pp\review_to_pp_gui.bat
```

자세한 입력 형식과 Premiere 임포트 방법: [`review_to_pp/README.md`](./review_to_pp/README.md)

## 🛠 시스템 요구사항

| 항목 | 요구사항 |
| :--- | :--- |
| Python | 3.10+ (3.12 권장) |
| OS | Windows 10/11 검증, macOS/Linux 호환 |
| RAM | 일반 사용 3GB+, Whisper large-v3 5GB+ |
| GPU (선택) | CUDA NVIDIA GPU, 4GB+ VRAM (transcriber 가속) |
| ffmpeg | 별도 설치 불필요 (`imageio-ffmpeg` 가 포함) |

## 🔐 회사망 / SSL 인터셉트 환경

기본적으로 SSL 검증을 비활성화하도록 설정되어 있어 MITM 프록시 환경에서도 동작합니다.

엄격 검증을 켜려면:
```powershell
$env:VERIFY_SSL = "1"
python transcriber/transcribe_gui.py
```

## 📁 디렉토리 구조

```
video_maker_tool/
├── README.md                    ← (이 파일)
├── requirements.txt             ← 모든 도구 통합 의존성
├── .gitignore
│
├── transcriber/                 ← 영상 → 자막
│   ├── transcribe.py            (CLI)
│   └── transcribe_gui.py        (GUI)
│
├── translator/                  ← 자막 번역
│   ├── deepl_translate_srt.py   (CLI 메인)
│   ├── deepl_gui.py             (GUI)
│   ├── deepl_gui.bat            (GUI 런처)
│   ├── translate_drop.bat       (드래그&드롭)
│   ├── translate_srt.py         (예전 버전 / 백업)
│   └── .deepl_key               (gitignore, API 키)
│
└── review_to_pp/                ← 리뷰 → Premiere XML
    ├── review_to_pp.py          (CLI)
    ├── review_to_pp_gui.py      (GUI)
    ├── review_to_pp_gui.bat
    ├── README.md
    └── examples/
```

## 📜 라이선스

개인 / 비상업적 사용 무제한. 회사 정책에 따라 사용.
