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

# ─── Model selection ────────────────────────────────

select_models() {
    echo ""
    echo "설치할 Ollama 모델을 선택하세요 (쉼표로 구분, 예: 1,3):"
    echo ""
    local i=1
    local default_idx=${#OLLAMA_MODELS[@]}
    for model in "${OLLAMA_MODELS[@]}"; do
        if [ "$i" -eq "$default_idx" ]; then
            echo "  ${i}) ${model}  (추천)"
        else
            echo "  ${i}) ${model}"
        fi
        i=$((i + 1))
    done
    echo ""
    read -rp "선택 [${default_idx}]: " model_choice
    model_choice="${model_choice:-$default_idx}"

    SELECTED_MODELS=()
    IFS=',' read -ra choices <<< "$model_choice"
    for c in "${choices[@]}"; do
        c="$(echo "$c" | tr -d ' ')"
        if ! [[ "$c" =~ ^[0-9]+$ ]]; then
            warn "잘못된 번호 무시: ${c}"
            continue
        fi
        idx=$((c - 1))
        if [ "$idx" -ge 0 ] && [ "$idx" -lt "${#OLLAMA_MODELS[@]}" ]; then
            SELECTED_MODELS+=("${OLLAMA_MODELS[$idx]}")
        else
            warn "잘못된 번호 무시: ${c}"
        fi
    done

    if [ "${#SELECTED_MODELS[@]}" -eq 0 ]; then
        warn "선택된 모델이 없습니다. 기본 모델(${OLLAMA_MODELS[0]})을 설치합니다."
        SELECTED_MODELS=("${OLLAMA_MODELS[0]}")
    fi
}

echo ""
echo "================================================"
echo "  FeedMePapers - Installation"
echo "================================================"
echo ""

# ─── Detect available tools ──────────────────────────

HAS_UV=false
HAS_CONDA=false
HAS_DOCKER=false

command -v uv &>/dev/null && HAS_UV=true
command -v conda &>/dev/null && HAS_CONDA=true
command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1 && HAS_DOCKER=true

# ─── Interactive menu ────────────────────────────────

echo "설치 방법을 선택하세요:"
echo ""

idx=1
MENU_ITEMS=""

if $HAS_UV; then
    echo "  ${idx}) uv       (빠른 Python 패키지 매니저)"
    MENU_ITEMS="${MENU_ITEMS}${idx}:uv "
    idx=$((idx + 1))
fi

if $HAS_CONDA; then
    echo "  ${idx}) conda"
    MENU_ITEMS="${MENU_ITEMS}${idx}:conda "
    idx=$((idx + 1))
fi

echo "  ${idx}) venv     (Python 내장)"
MENU_ITEMS="${MENU_ITEMS}${idx}:venv "
idx=$((idx + 1))

if $HAS_DOCKER; then
    echo "  ${idx}) Docker   (앱 + Ollama 컨테이너)"
    MENU_ITEMS="${MENU_ITEMS}${idx}:docker "
    idx=$((idx + 1))
fi

echo ""
read -rp "선택 [1]: " choice
choice="${choice:-1}"

INSTALL_METHOD=""
for item in $MENU_ITEMS; do
    key="${item%%:*}"
    val="${item#*:}"
    if [ "$key" = "$choice" ]; then
        INSTALL_METHOD="$val"
        break
    fi
done

if [ -z "$INSTALL_METHOD" ]; then
    fail "잘못된 선택입니다: ${choice}"
fi

info "선택: ${INSTALL_METHOD}"
echo ""

# ─── Install: uv ─────────────────────────────────────

install_uv() {
    info "Setting up uv environment..."

    if [ ! -d ".venv" ]; then
        uv venv --python "$PYTHON_VERSION"
        ok "venv created at .venv/ (via uv)"
    else
        ok "venv already exists."
    fi

    uv pip install --python .venv/bin/python -e .
    ok "Dependencies installed (editable mode). CLI command 'feedmepapers' registered."
}

# ─── Install: conda ──────────────────────────────────

install_conda() {
    info "Setting up conda environment..."

    if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
        ok "conda env '${CONDA_ENV_NAME}' already exists."
    else
        conda create -n "$CONDA_ENV_NAME" python="$PYTHON_VERSION" -y -q
        ok "conda env '${CONDA_ENV_NAME}' created (Python ${PYTHON_VERSION})."
    fi

    eval "$(conda shell.bash hook)"
    conda activate "$CONDA_ENV_NAME"

    info "Installing Python dependencies..."
    pip install -q -r requirements.txt
    ok "Python dependencies installed."
}

# ─── Install: venv ───────────────────────────────────

install_venv() {
    info "Setting up venv environment..."

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

    info "Installing Python dependencies..."
    pip install -q -r requirements.txt
    ok "Python dependencies installed."
}

# ─── Install: Docker ─────────────────────────────────

install_docker() {
    info "Setting up Docker environment..."

    # Config files
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

    info "Building Docker image..."
    docker compose build
    ok "Docker image built."

    info "Starting Ollama container..."
    docker compose up -d ollama
    ok "Ollama container started."

    info "Waiting for Ollama to be ready..."
    local retries=0
    while ! docker compose exec ollama ollama list >/dev/null 2>&1; do
        retries=$((retries + 1))
        if [ $retries -ge 30 ]; then
            fail "Ollama failed to start after 30 retries."
        fi
        sleep 2
    done
    ok "Ollama is ready."

    select_models
    info "Pulling models... (this may take a few minutes)"
    for model in "${SELECTED_MODELS[@]}"; do
        info "Pulling '${model}'..."
        docker compose exec ollama ollama pull "$model"
        ok "Model '${model}' ready."
    done

    ok "Docker setup complete."
    return
}

# ─── Run selected install method ─────────────────────

case "$INSTALL_METHOD" in
    uv)     install_uv ;;
    conda)  install_conda ;;
    venv)   install_venv ;;
    docker) install_docker ;;
esac

# ─── Ollama (non-Docker only) ────────────────────────

if [ "$INSTALL_METHOD" != "docker" ]; then
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

    select_models
    info "Pulling models... (this may take a few minutes)"

    for model in "${SELECTED_MODELS[@]}"; do
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
fi

# ─── Config files (non-Docker) ───────────────────────

if [ "$INSTALL_METHOD" != "docker" ]; then
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
fi

# ─── Done ────────────────────────────────────────────

echo ""
echo "================================================"
echo -e "  ${GREEN}Installation complete!${NC}"
echo "================================================"
echo ""
echo "  Next steps:"
echo ""

case "$INSTALL_METHOD" in
    uv)
        echo "  0. Python 환경 활성화"
        echo "     source .venv/bin/activate"
        echo "     (또는 uv run 으로 직접 실행 가능)"
        ;;
    conda)
        echo "  0. 새 터미널에서 Python 환경 활성화"
        echo "     conda activate ${CONDA_ENV_NAME}"
        echo "     (또는 단발 실행: conda run -n ${CONDA_ENV_NAME} python main.py)"
        ;;
    venv)
        echo "  0. 새 터미널에서 Python 환경 활성화"
        echo "     source .venv/bin/activate"
        ;;
    docker)
        echo "  0. Ollama가 이미 실행 중입니다"
        echo "     docker compose ps  # 상태 확인"
        ;;
esac

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

case "$INSTALL_METHOD" in
    uv)
        echo "     uv run feedmepapers --setup-notion-db YOUR_PAGE_ID"
        echo "     (DB가 자동 생성되고 .env에 ID가 저장됩니다)"
        echo ""
        echo "  5. config.yaml에서 검색 키워드 설정 후 실행"
        echo "     uv run feedmepapers"
        echo "     (또는: uv run python main.py)"
        ;;
    docker)
        echo "     docker compose run --rm app --setup-notion-db YOUR_PAGE_ID"
        echo "     (DB가 자동 생성되고 .env에 ID가 저장됩니다)"
        echo ""
        echo "  5. config.yaml에서 검색 키워드 설정 후 실행"
        echo "     docker compose run --rm app"
        ;;
    *)
        echo "     python main.py --setup-notion-db YOUR_PAGE_ID"
        echo "     (DB가 자동 생성되고 .env에 ID가 저장됩니다)"
        echo ""
        echo "  5. config.yaml에서 검색 키워드 설정 후 실행"
        echo "     python main.py"
        ;;
esac

echo ""
