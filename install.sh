#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
#  install.sh — Cài đặt tự động cho macOS (Apple Silicon)
#  Chạy: bash install.sh
#  Không cần biết lập trình!
# ════════════════════════════════════════════════════════════════

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Màu sắc terminal ──────────────────────────────────────────────────────────
G="\033[92m"; Y="\033[93m"; R="\033[91m"; C="\033[96m"; W="\033[97m"
B="\033[94m"; DIM="\033[2m"; BOLD="\033[1m"; END="\033[0m"

ok()   { echo -e "${G}  [OK] $*${END}"; }
warn() { echo -e "${Y}  [!]  $*${END}"; }
err()  { echo -e "${R}  [X]  $*${END}"; }
info() { echo -e "${C}  [i]  $*${END}"; }
hdr()  { echo -e "\n${B}${BOLD}── $* ──${END}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${B}${BOLD}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║     Meeting Transcriber — Cài đặt tự động macOS     ║"
echo "  ║   🇯🇵 Nhật  ·  🇬🇧 Anh  ·  🇻🇳 Việt  —  100% local  ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${END}"
echo -e "  Script này sẽ tự động:"
echo -e "    ${W}[1]${END} Cài Homebrew (nếu chưa có)"
echo -e "    ${W}[2]${END} Cài Python 3.11 (nếu chưa có)"
echo -e "    ${W}[3]${END} Cài Ollama (nếu chưa có)"
echo -e "    ${W}[4]${END} Tạo môi trường Python và cài thư viện"
echo -e "    ${W}[5]${END} Chạy wizard chọn model và cấu hình"
echo ""
read -p "  Nhấn Enter để bắt đầu..." _

# ── BƯỚC 1: Homebrew ──────────────────────────────────────────────────────────
hdr "Bước 1/4: Kiểm tra Homebrew"

if command -v brew &>/dev/null; then
    ok "Homebrew đã có: $(brew --version | head -1)"
else
    warn "Homebrew chưa được cài. Đang cài..."
    echo -e "  ${DIM}(Có thể hỏi mật khẩu macOS — đây là bình thường)${END}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Thêm Homebrew vào PATH cho Apple Silicon
    if [[ -f "/opt/homebrew/bin/brew" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi

    if command -v brew &>/dev/null; then
        ok "Homebrew đã cài xong!"
    else
        err "Không cài được Homebrew. Thử lại hoặc cài thủ công từ https://brew.sh"
        exit 1
    fi
fi

# ── BƯỚC 2: Python 3.11 ───────────────────────────────────────────────────────
hdr "Bước 2/4: Kiểm tra Python 3.11"

PYTHON=""
for cmd in python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oP '3\.(1[01]|9)' || true)
        if [[ "$ver" == "3.11" ]] || [[ "$ver" == "3.10" ]]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    info "Python 3.11 chưa có. Đang cài qua Homebrew..."
    brew install python@3.11
    PYTHON="$(brew --prefix)/bin/python3.11"
fi

ok "Python: $($PYTHON --version)"

# ── BƯỚC 3: Ollama ────────────────────────────────────────────────────────────
hdr "Bước 3/4: Kiểm tra Ollama"

if ! command -v ollama &>/dev/null; then
    info "Ollama chưa có. Đang cài qua Homebrew..."
    brew install ollama
    ok "Ollama đã cài xong!"
else
    ok "Ollama đã có: $(ollama --version 2>/dev/null || echo 'installed')"
fi

# Khởi động Ollama nếu chưa chạy
if ! curl -s http://localhost:11434 &>/dev/null; then
    info "Đang khởi động Ollama server..."
    brew services start ollama 2>/dev/null || ollama serve &>/dev/null &
    sleep 3
fi

if curl -s http://localhost:11434 &>/dev/null; then
    ok "Ollama server đang chạy"
else
    warn "Ollama chưa phản hồi — wizard sẽ thử pull model trực tiếp"
fi

# ── BƯỚC 4: Môi trường Python + thư viện ─────────────────────────────────────
hdr "Bước 4/4: Tạo môi trường Python và cài thư viện"

if [[ -f ".venv/bin/activate" ]]; then
    ok "Môi trường .venv đã tồn tại — bỏ qua tạo mới"
else
    info "Tạo môi trường ảo .venv ..."
    "$PYTHON" -m venv .venv
    ok "Tạo xong .venv"
fi

# Kích hoạt
source .venv/bin/activate
PYTHON_VENV="$SCRIPT_DIR/.venv/bin/python"

info "Cài thư viện Python (có thể mất 5–10 phút, tải ~2 GB)..."
echo -e "  ${DIM}Bao gồm: faster-whisper, pyannote, gradio, torch, sounddevice...${END}"

pip install --upgrade pip --quiet
pip install -r requirements.txt

ok "Cài đặt thư viện hoàn tất!"

# ── BƯỚC 5: Wizard cấu hình ───────────────────────────────────────────────────
echo ""
echo -e "${G}${BOLD}════════════════════════════════════════════════════════${END}"
echo -e "${G}${BOLD}  Sắp xong! Đang chạy wizard chọn model và cấu hình... ${END}"
echo -e "${G}${BOLD}════════════════════════════════════════════════════════${END}"
echo ""
sleep 2

"$PYTHON_VENV" setup_wizard.py

echo ""
echo -e "${G}${BOLD}  Cảm ơn đã cài đặt Meeting Transcriber!${END}"
echo -e "  Để chạy app sau này: ${C}bash run.sh${END} hoặc double-click trên Desktop"
echo ""
