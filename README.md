# FeedMePapers

> 📍 이 repo는 와니쨩✨ 의 아이디어를 바탕으로 제작되었음을 밝힙니다.

최신 논문을 자동으로 검색하고, 로컬 LLM으로 한국어 번역 및 핵심 요약을 생성한 뒤, Notion 데이터베이스에 정리해주는 도구입니다.

## Features

- **Dual Search** — Semantic Scholar API + arXiv API 동시 검색, 자동 중복 제거
- **학회 필터링** — CVPR, ICCV, NeurIPS, CoRL 등 원하는 학회만 필터링 (미설정 시 전체 검색)
- **로컬 LLM 번역** — Ollama 기반 로컬 LLM으로 초록 한국어 번역 + 핵심 novelty 요약 (2~3문장)
- **중국어 오염 방지** — Qwen 등 중국어 모델 사용 시 중국어 혼입 자동 감지/재시도/제거
- **Notion 자동 정리** — 논문 정보를 Notion 데이터베이스에 자동 등록, 중복 논문 skip
- **검색 메타데이터** — 검색 키워드, 검색 날짜 자동 기록

## 🚀 Quick Start

### 1. 설치

```bash
git clone https://github.com/RooibosT/FeedMePapers.git
cd FeedMePapers
bash install.sh
```

`install.sh`가 자동으로 처리하는 항목:
- conda 환경 생성 (없으면 venv fallback)
- Python 패키지 설치
- Ollama 설치 + 모델 다운로드 (`qwen2.5:7b`, `qwen3:8b`, `gemma2:9b`, `exaone3.5:7.8b`)
- `config.yaml` / `.env` 파일 생성 (예시 파일에서 자동 복사)

설치 스크립트가 끝난 뒤에는 **현재 터미널에서 Python 환경을 다시 활성화**해야 합니다:

```bash
conda activate feedmepapers
# 또는 단발 실행:
conda run -n feedmepapers python main.py
```

conda를 쓰지 않는 경우:

```bash
source .venv/bin/activate
```

### 2. Notion 연결 (수동)

Notion API는 토큰 발급이 필요하므로 수동으로 진행합니다.

**a)** [Notion Integrations](https://www.notion.so/profile/integrations)에서 **New integration** 생성 후 Token 복사

**b)** `.env` 파일에 토큰 입력

```env
NOTION_TOKEN=ntn_your_token_here
```

**c)** 논문을 정리할 Notion 페이지에서 `···` → **Connect to** → 생성한 integration 선택

**d)** 데이터베이스 자동 생성

```bash
python main.py --setup-notion-db YOUR_PAGE_ID
```

페이지 ID만 입력하면 데이터베이스가 자동 생성되고, `.env`에 DB ID가 자동 저장됩니다.

> **페이지 ID 찾기**: Notion 페이지 URL의 마지막 32자리 hex 값.
> `https://notion.so/myworkspace/Paper-AI-30c249225458...` → `30c24922-5458-80d0-...`

### 3. 검색 키워드 설정

`config.yaml`에서 본인의 연구 분야에 맞게 키워드를 수정합니다:

```yaml
keywords:
  - "embodied AI"
  - "robot navigation"
  - "visual navigation"
```

> **키워드 설정 팁**: AND 조합 키워드를 너무 많이 넣거나 세부 분야를 지나치게 좁게 설정하면 검색 결과가 적어질 수 있고, 반대로 너무 포괄적인 키워드는 주제를 벗어난 논문들이 섞일 수 있습니다. 자신의 연구 분야에 맞는 논문이 잘 검색되도록 여러 키워드 조합을 테스트해보세요! (귀찮으면 GPT/Gemini/Claude에게 키워드 추천을 부탁해보세요)

### 4. 실행

```bash
python main.py
```

실행할 때마다 기존 데이터베이스에 논문이 누적되며, 이미 등록된 논문은 자동으로 skip됩니다.

## Configuration

### config.yaml

```yaml
keywords:                         # 검색 키워드 (여러 개 가능)
  - "embodied AI"
  - "robot navigation"

date_range_days: 7                # 검색 기간 (최근 N일)
max_results_per_keyword: 20       # 키워드당 최대 결과 수

# 학회 필터 (비워두면 전체 검색)
venues:
  - "CVPR"
  - "ICCV"
  - "NeurIPS"
  # - "ECCV"
  # - "CoRL"
  # - "IROS"
  # - "ICRA"

llm:
  model: "qwen2.5:7b"            # Ollama 모델명
  base_url: "http://localhost:11434"
  temperature: 0.3                # 낮을수록 일관된 번역

notion:
  enabled: true                   # false면 Notion 저장 skip

output:
  console: true
  json_file: true
  json_dir: "results"
```

### config.yaml / .env

`config.yaml`과 `.env`는 개인 설정 파일이므로 git에 포함되지 않습니다. 예시 파일을 복사하여 생성하세요:

```bash
cp config.example.yaml config.yaml   # 검색 키워드, LLM 모델 등 설정
cp .env.example .env                 # Notion 토큰 등 시크릿
```

`.env` 파일 내용:

```env
NOTION_TOKEN=ntn_...              # Notion integration token
NOTION_DATABASE_ID=...            # --setup-notion-db로 자동 생성/저장
S2_API_KEY=                       # 선택사항 (rate limit 완화)
```

## Usage

```bash
python main.py                           # 전체 파이프라인 실행
python main.py -c my_config.yaml         # 다른 config 사용
python main.py --no-llm                  # LLM 번역 skip
python main.py --no-notion               # Notion 저장 skip
python main.py --setup-notion-db PAGE_ID # Notion DB 자동 생성
conda run -n feedmepapers python main.py # conda 미활성화 상태에서 단발 실행
PYTHONPATH=src python -m feedmepapers.cli --help  # 패키지 엔트리포인트(개발용)
```

### 정기 실행 (cron)

```cron
# 매주 월요일 오전 9시
0 9 * * 1 cd /path/to/FeedMePapers && /path/to/python main.py >> cron.log 2>&1
```

## Notion Database Schema

| Property | Type | 설명 |
|---|---|---|
| Title | Title | 논문 제목 |
| Authors | Rich Text | 1저자 + et al. |
| Venue | Select | 학회/저널명 |
| Date | Date | 논문 발표일 |
| URL | URL | 논문 링크 |
| ArXiv ID | Rich Text | arXiv 논문 ID |
| Abstract (KO) | Rich Text | 한국어 번역 초록 |
| Novelty | Rich Text | 핵심 novelty 한국어 요약 |
| Keywords | Multi Select | 검색에 사용된 키워드 |
| Searched | Date | 프로그램 실행일 |

페이지 본문에는 한국어 초록과 영어 원문 초록이 함께 포함됩니다.

## Project Structure

```
FeedMePapers/
├── src/
│   └── feedmepapers/
│       ├── cli.py               # 메인 CLI 로직
│       ├── config.py            # config 로더
│       ├── models.py            # 공통 데이터 모델(Paper)
│       ├── search/
│       │   └── searcher.py      # Semantic Scholar + arXiv 검색
│       ├── llm/
│       │   └── processor.py     # Ollama LLM 번역 + novelty 추출
│       └── notion/
│           └── publisher.py     # Notion 데이터베이스 퍼블리셔
├── install.sh              # 원클릭 설치 스크립트
├── main.py                 # 호환용 엔트리포인트 (기존 명령 유지)
├── config.yaml             # 검색/LLM/Notion 설정
├── .env.example            # 환경 변수 템플릿
├── requirements.txt        # Python 의존성
└── results/                # JSON 출력 디렉토리
```

## Troubleshooting

### Semantic Scholar Rate Limit (429)

API key 없이 사용 시 1req/s 제한. 자동 재시도 (최대 4회, exponential backoff) 적용. 키워드가 많으면 [API key 발급](https://www.semanticscholar.org/product/api#api-key-form) 권장.

### Ollama 연결 실패

```bash
curl http://localhost:11434/api/tags    # Ollama 상태 확인
docker ps | grep ollama                 # Docker인 경우
docker start ollama                     # 컨테이너 재시작
```

### 한국어 번역에 중국어 섞임

Qwen 모델 특성상 간헐적 발생. 자동 재시도 (2회) + 중국어 문자 제거 로직 적용. `config.yaml`에서 `llm.temperature`를 `0.1`로 낮추면 개선.

## GPU Requirements

| 모델 | VRAM | 비고 |
|---|---|---|
| qwen2.5:7b | ~5GB | 기본 권장 |
| qwen2.5:3b | ~2GB | 저사양 GPU |
| gemma2:9b | ~6GB | 중국어 오염 없음 |

`config.yaml`의 `llm.model`을 변경하여 다른 모델 사용 가능.

## License

MIT
