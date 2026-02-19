# FeedMePapers

최신 논문을 자동으로 검색하고, 로컬 LLM으로 한국어 번역 및 핵심 요약을 생성한 뒤, Notion 데이터베이스에 정리해주는 도구입니다.

## Features

- **Dual Search** — Semantic Scholar API + arXiv API 동시 검색, 자동 중복 제거
- **학회 필터링** — CVPR, ICCV, NeurIPS, CoRL 등 원하는 학회만 필터링 (미설정 시 전체 검색)
- **로컬 LLM 번역** — Ollama 기반 로컬 LLM으로 초록 한국어 번역 + 핵심 novelty 요약 (2~3문장)
- **중국어 오염 방지** — Qwen 등 중국어 모델 사용 시 중국어 혼입 자동 감지/재시도/제거
- **Notion 자동 정리** — 논문 정보를 Notion 데이터베이스에 자동 등록, 중복 논문 skip
- **검색 메타데이터** — 검색 키워드, 검색 날짜 자동 기록

## Notion Database Schema

| Property | Type | 설명 |
|---|---|---|
| Title | Title | 논문 제목 |
| Authors | Rich Text | 1저자 + et al. (소속 있으면 포함) |
| Venue | Select | 학회/저널명 |
| Date | Date | 논문 발표일 |
| URL | URL | 논문 링크 |
| ArXiv ID | Rich Text | arXiv 논문 ID |
| Abstract (KO) | Rich Text | 한국어 번역 초록 |
| Novelty | Rich Text | 핵심 novelty 한국어 요약 |
| Keywords | Multi Select | 검색에 사용된 키워드 |
| Searched | Date | 프로그램 실행일 (조사 날짜) |

페이지 본문에는 한국어 초록과 영어 원문 초록이 함께 포함됩니다.

## Prerequisites

### 1. Ollama

로컬 LLM 서버가 필요합니다. Docker 또는 네이티브 설치 중 택일:

```bash
# Docker (권장, GPU 사용)
docker run -d --gpus=all -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama:latest

# 모델 다운로드
docker exec ollama ollama pull qwen2.5:7b
```

```bash
# 네이티브 설치
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b
```

> **GPU VRAM**: Qwen2.5:7b 기준 약 5GB. 10GB 이하 GPU에서 동작 가능.
>
> 다른 모델도 사용 가능합니다. `config.yaml`에서 `llm.model`을 변경하세요.

### 2. Notion API

1. [Notion Integrations](https://www.notion.so/profile/integrations)에서 **New integration** 생성
2. Capabilities에서 **Read content**, **Insert content**, **Update content** 활성화
3. Internal Integration Token 복사 (`ntn_` 또는 `secret_`으로 시작)
4. 논문을 정리할 Notion 페이지에서 `···` → **Connect to** → 생성한 integration 연결

### 3. Python

Python 3.10+ 필요.

## Installation

```bash
git clone https://github.com/RooibosT/FeedMePapers.git
cd FeedMePapers

# 가상환경 생성 (conda 또는 venv)
conda create -n feedmepapers python=3.11 -y
conda activate feedmepapers
# 또는
# python -m venv .venv && source .venv/bin/activate

pip install -r requirements.txt
```

## Configuration

### 1. 환경 변수 (.env)

```bash
cp .env.example .env
```

`.env` 파일을 열어 Notion 토큰을 입력합니다:

```env
NOTION_TOKEN=ntn_your_token_here
NOTION_DATABASE_ID=           # 아래 setup 단계에서 자동 생성
S2_API_KEY=                   # 선택사항 (없어도 동작, 있으면 rate limit 완화)
```

### 2. Notion 데이터베이스 생성

논문을 정리할 Notion 페이지의 ID를 찾아 아래 명령을 실행합니다:

```bash
# 페이지 URL에서 ID 확인: https://notion.so/workspace/PAGE_ID
python main.py --setup-notion-db YOUR_PAGE_ID
```

출력된 `NOTION_DATABASE_ID`를 `.env`에 추가합니다.

> **페이지 ID 찾기**: Notion 페이지 URL의 마지막 32자리 hex 값이 페이지 ID입니다.
> 예: `https://notion.so/myworkspace/Paper-AI-30c249225458...` → `30c24922-5458-...`

### 3. 검색 설정 (config.yaml)

```yaml
# 검색 키워드 (여러 개 가능)
keywords:
  - "embodied AI"
  - "robot navigation"
  - "visual navigation"

# 검색 기간 (최근 N일)
date_range_days: 7

# 키워드당 최대 검색 결과 수
max_results_per_keyword: 20

# 학회 필터 (비워두면 전체 검색)
venues:
  - "CVPR"
  - "ICCV"
  - "NeurIPS"
  # - "ECCV"
  # - "CoRL"
  # - "IROS"
  # - "ICRA"

# 로컬 LLM 설정
llm:
  provider: "ollama"
  model: "qwen2.5:7b"
  base_url: "http://localhost:11434"
  timeout: 120
  temperature: 0.3

# Notion 설정
notion:
  enabled: true

# 출력 설정
output:
  console: true
  json_file: true
  json_dir: "results"
```

## Usage

### 기본 실행

```bash
python main.py
```

실행 흐름:
1. Semantic Scholar + arXiv에서 논문 검색
2. Ollama LLM으로 한국어 번역 + novelty 요약
3. Notion 데이터베이스에 등록 (중복 자동 skip)
4. `results/` 디렉토리에 JSON 저장

### 옵션

```bash
# 다른 config 파일 사용
python main.py -c my_config.yaml

# LLM 번역 없이 검색 + Notion 등록만
python main.py --no-llm

# Notion 없이 검색 + 번역만 (JSON 저장)
python main.py --no-notion

# Notion DB 새로 생성
python main.py --setup-notion-db PAGE_ID
```

### 정기 실행 (cron)

매주 월요일 오전 9시에 자동 실행:

```bash
crontab -e
```

```cron
0 9 * * 1 cd /path/to/FeedMePapers && /path/to/conda/envs/feedmepapers/bin/python main.py >> cron.log 2>&1
```

## Project Structure

```
FeedMePapers/
├── main.py               # CLI 엔트리포인트 & 파이프라인 오케스트레이터
├── searcher.py            # Semantic Scholar + arXiv 검색 모듈
├── llm_processor.py       # Ollama LLM 한국어 번역 + novelty 추출
├── notion_publisher.py    # Notion 데이터베이스 퍼블리셔
├── config.yaml            # 검색/LLM/Notion 설정
├── .env.example           # 환경 변수 템플릿
├── requirements.txt       # Python 의존성
└── results/               # JSON 출력 디렉토리
```

## Troubleshooting

### Semantic Scholar Rate Limit (429)

API key 없이 사용 시 1req/s 제한. 자동 재시도 (최대 4회, exponential backoff) 하지만, 키워드가 많으면 [API key 발급](https://www.semanticscholar.org/product/api#api-key-form) 권장.

### Ollama 연결 실패

```bash
# Docker 상태 확인
docker ps | grep ollama

# 모델 확인
docker exec ollama ollama list

# 직접 테스트
curl http://localhost:11434/api/tags
```

### 한국어 번역에 중국어 섞임

Qwen 모델 특성상 간헐적으로 발생. 자동 재시도 (2회) + 중국어 문자 제거 로직이 적용되어 있습니다. 심하면 `config.yaml`에서 `llm.temperature`를 `0.1`로 낮춰보세요.

### Notion "NOTION_TOKEN is required"

`.env` 파일이 프로젝트 루트에 있는지 확인하세요. `cp .env.example .env` 후 토큰 입력.

## License

MIT
