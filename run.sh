#!/usr/bin/env bash
# run.sh — Khởi động Meeting Transcriber trên macOS/Linux
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f ".venv/bin/activate" ]; then
    echo "[ERROR] Chưa tìm thấy .venv — Chạy setup trước:"
    echo "  python3.11 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Đảm bảo Ollama đang chạy (macOS)
if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! pgrep -x "ollama" > /dev/null 2>&1; then
        echo "[INFO] Khởi động Ollama..."
        brew services start ollama 2>/dev/null || ollama serve &
        sleep 2
    fi
fi

echo "[OK] Kích hoạt môi trường ảo..."
source .venv/bin/activate

echo "[OK] Đang khởi động app..."
python app.py
