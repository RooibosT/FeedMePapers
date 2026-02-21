#!/usr/bin/env bash
set -euo pipefail

CONDA_ENV_NAME="feedmepapers"
PYTHON_VERSION="3.11"
OLLAMA_MODELS=("qwen2.5:7b" "qwen3:8b" "gemma2:9b" "exaone3.5:7.8b")

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
PY_ENV_TYPE=""

echo ""
echo "================================================"
echo "  FeedMePapers - Installation"
echo "================================================"
echo ""

# ─── 1. Python environment ───────────────────────────

info "Setting up Python environment..."

if command -v conda &>/dev/null; then
    info "conda found. Creating environment '${CONDA_ENV_NAME}'..."

    if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
        ok "conda env '${CONDA_ENV_NAME}' already exists."
    else
        conda create -n "$CONDA_ENV_NAME" python="$PYTHON_VERSION" -y -q
        ok "conda env '${CONDA_ENV_NAME}' created (Python ${PYTHON_VERSION})."
    fi

    eval "$(conda shell.bash hook)"
    conda activate "$CONDA_ENV_NAME"
    PY_ENV_TYPE="conda"
else
    warn "conda not found. Using venv instead."

    if ! command -v python3 &>/dev/null; then
        fail "python3 not found. Install Python ${PYTHON_VERSION}+ first."
    fi

    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    info "Found Python ${PY_VER}"

    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
        ok "venv created at .venv/"
    else
        ok "venv already exists."
    fi

    source .venv/bin/activate
    PY_ENV_TYPE="venv"
fi

info "Installing Python dependencies..."
pip install -q -r requirements.txt
ok "Python dependencies installed."

# ─── 2. Ollama ────────────────────────────────────────

echo ""
info "Setting up Ollama..."

if command -v ollama &>/dev/null; then
    ok "Ollama already installed."
elif docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^ollama$"; then
    ok "Ollama Docker container found."
    if ! docker ps --format '{{.Names}}' | grep -q "^ollama$"; then
        info "Starting Ollama container..."
        docker start ollama
    fi
else
    info "Installing Ollama..."

    if [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "darwin"* ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
        ok "Ollama installed."
    else
        warn "Auto-install not supported on this OS."
        warn "Install manually: https://ollama.com/download"
        warn "Or use Docker: docker run -d --gpus=all -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama:latest"
    fi
fi

info "Pulling models... (this may take a few minutes)"

for model in "${OLLAMA_MODELS[@]}"; do
    info "Pulling '${model}'..."
    if command -v ollama &>/dev/null; then
        ollama pull "$model"
    elif docker ps --format '{{.Names}}' | grep -q "^ollama$"; then
        docker exec ollama ollama pull "$model"
    else
        warn "Could not pull model. Start Ollama and run: ollama pull ${model}"
        break
    fi
    ok "Model '${model}' ready."
done

# ─── 3. Config files ──────────────────────────────────

echo ""
if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    ok "config.yaml created from config.example.yaml"
else
    ok "config.yaml already exists."
fi

if [ ! -f .env ]; then
    cp .env.example .env
    ok ".env created from .env.example"
else
    ok ".env already exists."
fi

# ─── Done ─────────────────────────────────────────────

echo ""
echo "================================================"
echo -e "  ${GREEN}Installation complete!${NC}"
echo "================================================"
echo ""
echo "  Next steps:"
echo ""
if [ "$PY_ENV_TYPE" = "conda" ]; then
    echo "  0. 새 터미널에서 Python 환경 활성화"
    echo "     conda activate ${CONDA_ENV_NAME}"
    echo "     (또는 단발 실행: conda run -n ${CONDA_ENV_NAME} python main.py)"
else
    echo "  0. 새 터미널에서 Python 환경 활성화"
    echo "     source .venv/bin/activate"
fi
echo ""
echo "  1. Notion integration 생성"
echo "     https://www.notion.so/profile/integrations"
echo "     → New integration → Token 복사"
echo ""
echo "  2. .env에 토큰 입력"
echo "     NOTION_TOKEN=ntn_your_token_here"
echo ""
echo "  3. Notion 페이지에 integration 연결"
echo "     페이지 ··· → Connect to → 생성한 integration 선택"
echo ""
echo "  4. Notion 데이터베이스 자동 생성"
echo "     python main.py --setup-notion-db YOUR_PAGE_ID"
echo "     (DB가 자동 생성되고 .env에 ID가 저장됩니다)"
echo ""
echo "  5. config.yaml에서 검색 키워드 설정 후 실행"
echo "     python main.py"
echo ""
