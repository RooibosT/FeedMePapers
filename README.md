# FeedMePapers

최신 논문을 자동으로 검색하고, 로컬 LLM으로 한국어 번역 및 핵심 요약을 생성한 뒤, Notion 데이터베이스에 정리해주는 도구입니다.

## Features

- **Dual Search** — Semantic Scholar API + arXiv API 동시 검색, 자동 중복 제거
- **학회 필터링** — CVPR, ICCV, NeurIPS, CoRL 등 원하는 학회만 필터링 (미설정 시 전체 검색)
- **로컬 LLM 번역** — Ollama 기반 로컬 LLM으로 초록 한국어 번역 + 핵심 novelty 요약 (2~3문장)
- **중국어 오염 방지** — Qwen 등 중국어 모델 사용 시 중국어 혼입 자동 감지/재시도/제거
- **Notion 자동 정리** — 논문 정보를 Notion 데이터베이스에 자동 등록, 중복 논문 skip
- **검색 메타데이터** — 검색 키워드, 검색 날짜 자동 기록

## Quick Start

### 1. 설치

```bash
git clone https://github.com/RooibosT/FeedMePapers.git
cd FeedMePapers
bash install.sh
```

`install.sh`가 자동으로 처리하는 항목:
- conda 환경 생성 (없으면 venv fallback)
- Python 패키지 설치
- Ollama 설치 + 모델 다운로드 (`qwen2.5:7b`)
- `.env` 파일 생성

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

### .env

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
├── install.sh              # 원클릭 설치 스크립트
├── main.py                 # CLI 엔트리포인트
├── searcher.py             # Semantic Scholar + arXiv 검색
├── llm_processor.py        # Ollama LLM 번역 + novelty 추출
├── notion_publisher.py     # Notion 데이터베이스 퍼블리셔
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
