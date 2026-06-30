# Hướng dẫn cài đặt — macOS (Apple Silicon)

> Tài liệu này hướng dẫn từng bước để chạy Meeting Transcriber trên Mac với chip M1/M2/M3.  
> Ước tính thời gian: **20–30 phút** (phần lớn là chờ tải model).

---

## Mục lục

1. [Cài Homebrew](#1-cài-homebrew)
2. [Cài Python 3.11](#2-cài-python-311)
3. [Cài Ollama & kéo model LLM](#3-cài-ollama--kéo-model-llm)
4. [Cài project & Python dependencies](#4-cài-project--python-dependencies)
5. [Cấu hình HuggingFace Token](#5-cấu-hình-huggingface-token)
6. [Cài BlackHole để ghi âm hệ thống](#6-cài-blackhole-để-ghi-âm-hệ-thống-zoom--teams--meet)
7. [Chạy app lần đầu](#7-chạy-app-lần-đầu)
8. [Kiểm tra nhanh](#8-kiểm-tra-nhanh)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Cài Homebrew

Homebrew là package manager cho macOS — cần để cài Python, Ollama, BlackHole.

```bash
# Kiểm tra đã có chưa
brew --version

# Nếu chưa có, cài:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Sau khi cài, làm theo hướng dẫn trên màn hình để thêm brew vào PATH (thường là thêm 2 dòng vào `~/.zprofile`).

---

## 2. Cài Python 3.11

```bash
brew install python@3.11

# Kiểm tra
python3.11 --version
# → Python 3.11.x
```

> ⚠️ macOS đi kèm Python 3.9/3.10 hệ thống — đừng dùng cái đó. Dùng đúng `python3.11`.

---

## 3. Cài Ollama & kéo model LLM

Ollama là runtime để chạy các LLM (Qwen2.5, Llama, v.v.) local.

```bash
# Cài Ollama
brew install ollama

# Khởi động Ollama server (terminal 1 — giữ mở)
ollama serve
```

Mở **terminal mới** (terminal 2):

```bash
# Kéo model Qwen2.5 7B (~4.7 GB — cần chờ)
ollama pull qwen2.5:7b-instruct

# Xác nhận đã có
ollama list
# → NAME                    ID            SIZE   MODIFIED
# → qwen2.5:7b-instruct    xxxxxxxxxxxx  4.7 GB  ...
```

> 💡 `ollama serve` phải chạy mỗi khi bạn dùng app. Có thể đặt nó tự khởi động:
> ```bash
> # Thêm vào launchd (tự chạy lúc login)
> brew services start ollama
> ```

---

## 4. Cài project & Python dependencies

```bash
# Di chuyển vào thư mục project
cd "/path/to/transcript meeting"

# Tạo môi trường ảo (virtual environment)
python3.11 -m venv .venv

# Kích hoạt
source .venv/bin/activate
# Dấu nhắc sẽ đổi thành: (.venv) user@Mac $

# Cài tất cả thư viện (~vài phút, tải ~2 GB)
pip install -r requirements.txt
```

**Các thư viện chính sẽ được cài:**

```
faster-whisper    — nhận dạng giọng nói (Whisper large-v3)
pyannote.audio    — phân tách người nói
torch             — PyTorch (CPU backend cho Apple Silicon)
gradio            — web UI
sounddevice       — ghi âm
imageio-ffmpeg    — xử lý audio/video (kèm ffmpeg binary)
requests          — gọi Ollama API
python-dotenv     — đọc file .env
```

> ⏳ Bước `pip install` sẽ tải thêm các model nhỏ trong lần chạy đầu tiên (~1–3 GB).

---

## 5. Cấu hình HuggingFace Token

Token này cần để tải model **pyannote.audio** (phân tách người nói). Miễn phí.

### Bước 5.1 — Đăng ký HuggingFace

Vào https://huggingface.co → **Sign Up** → xác nhận email.

### Bước 5.2 — Chấp nhận điều khoản 2 model

Phải làm **cả hai**, nếu không pyannote sẽ báo lỗi 403:

```
→ https://huggingface.co/pyannote/speaker-diarization-3.1
  Click "Agree and access repository"

→ https://huggingface.co/pyannote/segmentation-3.0
  Click "Agree and access repository"
```

### Bước 5.3 — Tạo Access Token

1. Vào https://huggingface.co/settings/tokens
2. Click **"New token"**
3. Đặt tên (ví dụ: `meeting-transcriber`)
4. Loại: **Read** (không cần Write)
5. Click **Generate** → copy token (bắt đầu bằng `hf_...`)

### Bước 5.4 — Lưu vào .env

```bash
# Trong thư mục project
cp .env.example .env

# Mở bằng bất kỳ editor nào
open -e .env   # mở bằng TextEdit
# hoặc
nano .env
```

Sửa dòng:
```env
HF_TOKEN=hf_xxxxxxxx  →  HF_TOKEN=hf_AbCdEf123456...   (token thật của bạn)
```

---

## 6. Cài BlackHole để ghi âm hệ thống (Zoom / Teams / Meet)

BlackHole là virtual audio driver miễn phí — tạo ra một "ống" âm thanh ảo để ghi lại tiếng phát ra từ loa/tai nghe.

### Bước 6.1 — Cài BlackHole 2ch

```bash
brew install blackhole-2ch
```

Sau khi cài, **không cần restart** Mac.

### Bước 6.2 — Tạo Multi-Output Device

Mục tiêu: vừa **nghe** âm thanh qua loa/tai nghe, vừa **ghi** qua BlackHole.

```
1. Mở: Finder → Applications → Utilities → Audio MIDI Setup
   (hoặc Spotlight: Cmd+Space → gõ "Audio MIDI Setup")

2. Nhấn nút [+] ở góc dưới trái màn hình
   → Chọn "Create Multi-Output Device"

3. Một thiết bị mới "Multi-Output Device" xuất hiện bên trái.
   Tích chọn 2 thiết bị ở bảng bên phải:
   ☑ MacBook Pro Speakers  (hoặc "Built-in Output" / tai nghe của bạn)
   ☑ BlackHole 2ch

4. Double-click tên thiết bị → đổi tên thành "Meeting Capture"

5. Ở cột "Master" bên phải:
   → Chọn BlackHole 2ch làm master clock (tránh lệch sample rate)
```

### Bước 6.3 — Đặt làm output hệ thống khi họp

```
System Settings → Sound → Output
→ Chọn "Meeting Capture"
```

Sau cuộc họp, nhớ đổi lại loa thật (hoặc tạo phím tắt trong Sound settings).

### Bước 6.4 — Trong app

Ở tab **Đầu vào** → Chế độ ghi âm → Chọn thiết bị: **BlackHole 2ch**

```
┌─────────────────────────────────────────────────────┐
│ Luồng âm thanh khi họp:                             │
│                                                     │
│  Zoom/Teams  ──► Multi-Output Device ──► Loa/Tai nghe (bạn nghe)
│                        │                            │
│                        └──► BlackHole 2ch ──► App ghi lại
└─────────────────────────────────────────────────────┘
```

---

## 7. Chạy app lần đầu

```bash
# Kích hoạt môi trường ảo (nếu chưa)
source .venv/bin/activate

# Chạy
python app.py
```

Terminal sẽ hiển thị:
```
INFO  — Loading Whisper model 'large-v3' …    ← lần đầu tải ~3 GB
INFO  — Using device=cpu, compute_type=int8
Running on local URL: http://0.0.0.0:7860
```

Mở trình duyệt tại **http://localhost:7860**

> 🕐 **Lần đầu chạy:** Whisper (~3GB) và pyannote (~1GB) sẽ tự tải về `~/.cache/huggingface/`.  
> Từ lần 2 trở đi, load từ cache — chỉ mất vài giây.

---

## 8. Kiểm tra nhanh

Chạy unit tests (không cần sample file, không cần Ollama):

```bash
source .venv/bin/activate
pytest tests/test_pipeline.py::TestAlign -v
pytest tests/test_pipeline.py::TestConvert -v
pytest tests/test_pipeline.py::TestConfig -v
```

Kết quả mong đợi:
```
tests/test_pipeline.py::TestAlign::test_align_merge_basic PASSED
tests/test_pipeline.py::TestAlign::test_align_merge_no_turns PASSED
tests/test_pipeline.py::TestAlign::test_align_to_text_format PASSED
tests/test_pipeline.py::TestAlign::test_collapse_consecutive_speakers PASSED
tests/test_pipeline.py::TestConvert::test_ffmpeg_available PASSED
tests/test_pipeline.py::TestConfig::test_config_loads PASSED
```

---

## 9. Troubleshooting

### ❌ `brew: command not found`
Homebrew chưa được thêm vào PATH. Làm theo hướng dẫn cuối màn hình sau khi cài, hoặc:
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
source ~/.zprofile
```

---

### ❌ `python3.11: command not found`
```bash
# Tìm đường dẫn thật
ls /opt/homebrew/bin/python3.11
# Nếu có, thêm vào PATH:
echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zprofile && source ~/.zprofile
```

---

### ❌ `Cannot connect to Ollama at http://localhost:11434`
Ollama chưa chạy:
```bash
# Kiểm tra trạng thái
brew services info ollama

# Khởi động
brew services start ollama
# hoặc thủ công:
ollama serve &
```

---

### ❌ `401 Unauthorized` hoặc `403 Forbidden` (pyannote)
- Kiểm tra `HF_TOKEN` trong `.env` có đúng không
- Xác nhận bạn đã accept terms của **cả 2 model**:
  - https://huggingface.co/pyannote/speaker-diarization-3.1
  - https://huggingface.co/pyannote/segmentation-3.0

---

### ❌ Không nghe được âm thanh sau khi đặt Multi-Output Device
```
System Settings → Sound → Output
→ Tăng volume
→ Đảm bảo "MacBook Pro Speakers" được tích trong Multi-Output Device
→ Đảm bảo mute không được bật
```

---

### ❌ App ghi âm nhưng file trống / không có tiếng
- Kiểm tra đã chọn **Meeting Capture** làm output hệ thống chưa
- Mở **System Preferences → Sound → Input** → chọn **BlackHole 2ch** → thử nói và xem thanh level có nhảy không
- Thử record 10 giây rồi mở file WAV trong QuickTime để kiểm tra

---

### ❌ `torch.multiprocessing` lỗi hoặc crash
```bash
# Giới hạn số thread (fix lỗi oversubscription trên Apple Silicon)
export OMP_NUM_THREADS=4
python app.py
```

---

### 🐢 Transcribe quá chậm
- Dùng model nhỏ hơn: trong `.env` đặt `WHISPER_MODEL=medium` hoặc `small`
- Đóng các app nặng khác đang dùng nhiều RAM (Chrome, Final Cut, v.v.)
- Whisper chạy trên CPU — Apple M2 Pro/Max/Ultra nhanh hơn M1 base đáng kể

---

### 🔄 Reset môi trường (nếu mọi thứ hỏng)
```bash
# Xóa venv và cài lại từ đầu
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
