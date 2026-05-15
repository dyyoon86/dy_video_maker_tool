# review_to_pp

리뷰 스크립트(.txt / .json / .csv)를 **Adobe Premiere Pro XML + SRT 자막**으로 변환하는 도구.

영화 리뷰 유튜버를 위해 만들었어요. 타임스탬프가 박힌 리뷰 텍스트만 있으면 → 프리미어에서 바로 임포트 가능한 시퀀스 + 마커 + 자막 파일을 한 번에 생성합니다.

## ✨ 기능

- **3가지 입력 형식 지원**: `.txt` / `.json` / `.csv`
- **Final Cut Pro 7 XML 출력**: Premiere Pro `파일 > 가져오기`로 바로 임포트
- **자동 마커 생성**: 타임스탬프마다 시퀀스 마커 + 비트 라벨/내용 포함
- **SRT 자막 자동 생성**: 한국어 발화 속도 기준 자동 타이밍 계산
- **CLI + GUI 둘 다 제공**

## 🚀 빠른 시작

### CLI

```powershell
# 가장 간단한 사용
python review_to_pp.py examples\sample_review.txt

# 출력 폴더 지정
python review_to_pp.py examples\sample_review.json -o D:\output\

# 영상 경로/제목 덮어쓰기
python review_to_pp.py examples\sample_review.txt --video "D:\videos\my.mp4" --title "다른 제목"
```

결과물:
- `<입력파일명>_markers.xml` → 프리미어 임포트용
- `<입력파일명>_narration.srt` → 자막 파일

### GUI

```powershell
python review_to_pp_gui.py
```

또는 `review_to_pp_gui.bat` 더블클릭.

## 📝 입력 형식

### 1. 텍스트 (.txt) - 가장 간단

```text
[제목] 영화 제목
[영상] C:\path\to\video.mp4
[해상도] 1920x1080
[프레임레이트] 30

자유로운 인트로 문장...
오늘 소개할 영화는...

(00:28) 첫 번째 비트 내레이션
(01:00) 두 번째 비트 내레이션
(01:00:04) 시간 단위(HH:MM:SS)도 자동 인식
```

규칙:
- `[키] 값` 형식이 메타데이터 (제목/영상/해상도/프레임레이트)
- 타임스탬프 등장 전 줄 = **인트로**
- `(HH:MM:SS)` 또는 `(MM:SS)` 뒤의 문장 = **비트**

### 2. JSON (.json) - 정밀 제어

```json
{
  "title": "영화 제목",
  "video_path": "C:\\path\\to\\video.mp4",
  "framerate": 30,
  "resolution": [1920, 1080],
  "intro": "인트로 내레이션",
  "beats": [
    {"time": "00:28", "label": "인물 소개", "text": "..." },
    {"time": "01:00", "label": "사건 발단", "text": "..." }
  ]
}
```

### 3. CSV (.csv) - 엑셀에서 편집

```csv
# [제목] 영화 제목
# [영상] C:\path\to\video.mp4
time,label,text
00:00,인트로,"인트로 내레이션"
00:28,인물 소개,"첫 번째 비트"
01:00,사건 발단,"두 번째 비트"
```

`#` 으로 시작하는 줄은 메타데이터.

## 🎬 프리미어에서 사용하기

1. 프리미어 켜기 → **파일 > 새 프로젝트**
2. **파일 > 가져오기** (Ctrl+I) → `*_markers.xml` 선택
3. 프로젝트 패널에 시퀀스 자동 생성됨
4. 시퀀스 더블클릭 → 타임라인에 영상 + 마커 좌르륵 표시
5. **Shift+M** 으로 마커 사이 점프하며 편집
6. (선택) **파일 > 가져오기** → `*_narration.srt` → 자막 트랙으로 사용

### "미디어 오프라인" 빨간 화면이 떴다면

영상 파일이 XML에 지정된 경로에 없을 때 발생. 우클릭 → **미디어 연결(Link Media)** → 실제 영상 파일 선택.

## 🔧 시간 표기 규칙

| 입력 | 해석 |
| :--- | :--- |
| `00:28` | 28초 (MM:SS) |
| `01:00` | 60초 (MM:SS) |
| `01:00:04` | 1시간 4초 (HH:MM:SS) |
| `01:04:12` | 1시간 4분 12초 (HH:MM:SS) |

콜론(`:`)의 개수로 자동 판별.

## 📦 요구 사항

- Python 3.8 이상
- (GUI만) PyQt6: `pip install -r requirements.txt`

## 📁 디렉토리 구조

```
review_to_pp/
├── review_to_pp.py       # CLI 메인 스크립트
├── review_to_pp_gui.py   # GUI (PyQt6)
├── review_to_pp_gui.bat  # GUI 실행 배치
├── requirements.txt
├── README.md
├── examples/
│   ├── sample_review.txt
│   ├── sample_review.json
│   └── sample_review.csv
└── output/               # 변환 결과물 기본 저장 위치
```

## 💡 팁

- 영상 파일 경로는 **영문 경로 추천** (한글 경로는 가끔 인식 안 됨)
- 한 번 만든 XML은 영상 파일이 그 경로에 계속 있어야 정상 작동
- 10개 영상 일괄 처리는 PowerShell 루프로:
  ```powershell
  Get-ChildItem .\scripts\*.txt | ForEach-Object { python review_to_pp.py $_.FullName -o .\output\ }
  ```
