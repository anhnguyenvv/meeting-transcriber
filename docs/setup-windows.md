# Hướng dẫn cài đặt — Windows 11

> Tài liệu này hướng dẫn từng bước để chạy Meeting Transcriber trên Windows 11.  
> Ước tính thời gian: **25–35 phút** (phần lớn là chờ tải model).

---

## Mục lục

1. [Cài Python 3.11](#1-cài-python-311)
2. [Cài Ollama & kéo model LLM](#2-cài-ollama--kéo-model-llm)
3. [Cài project & Python dependencies](#3-cài-project--python-dependencies)
4. [Cấu hình HuggingFace Token](#4-cấu-hình-huggingface-token)
5. [Cài VB-CABLE để ghi âm hệ thống](#5-cài-vb-cable-để-ghi-âm-hệ-thống-zoom--teams--meet)
6. [Tăng tốc với NVIDIA GPU (tùy chọn)](#6-tăng-tốc-với-nvidia-gpu-tùy-chọn)
7. [Chạy app lần đầu](#7-chạy-app-lần-đầu)
8. [Kiểm tra nhanh](#8-kiểm-tra-nhanh)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Cài Python 3.11

### Tải bản cài đặt

1. Vào https://www.python.org/downloads/release/python-3119/
2. Kéo xuống phần **"Files"**, chọn **"Windows installer (64-bit)"**
3. Chạy file `.exe` vừa tải

### Cài đặt (quan trọng!)

```
┌─────────────────────────────────────────────────────┐
│  Install Python 3.11                                │
│                                                     │
│  ☑  Add Python 3.11 to PATH    ← BẮT BUỘC phải tích│
│                                                     │
│  [ Install Now ]   [ Customize installation ]       │
└─────────────────────────────────────────────────────┘
```

> ⚠️ Nếu quên tích "Add to PATH", phải gỡ cài đặt và cài lại!

### Kiểm tra

Mở **Command Prompt** (Win+R → `cmd` → Enter):

```cmd
python --version
```
→ Phải ra `Python 3.11.x`

---

## 2. Cài Ollama & kéo model LLM

### Cài Ollama

1. Tải tại https://ollama.com/download → **Download for Windows**
2. Chạy file `.exe` → cài như phần mềm bình thường (Next → Next → Install)
3. Ollama tự khởi động và chạy ngầm (icon ở System Tray góc dưới phải)

### Kéo model Qwen2.5 7B (~4.7 GB)

Mở **PowerShell** hoặc **Command Prompt**:

```powershell
# Kéo model (sẽ mất 5–15 phút tùy tốc độ mạng)
ollama pull qwen2.5:7b-instruct

# Kiểm tra đã có
ollama list
```

Kết quả mong đợi:
```
NAME                    ID            SIZE    MODIFIED
qwen2.5:7b-instruct    xxxxxxxxxxxx  4.7 GB  x minutes ago
```

> 💡 Ollama tự khởi động cùng Windows. Nếu muốn kiểm tra đang chạy:
> ```powershell
> curl http://localhost:11434/api/tags
> # → {"models":[...]}  ← OK
> ```

---

## 3. Cài project & Python dependencies

Mở **PowerShell** (không cần quyền Admin):

```powershell
# Di chuyển vào thư mục project
cd "D:\project\transcript meeting"

# Tạo môi trường ảo (virtual environment)
python -m venv .venv

# Kích hoạt môi trường ảo
.venv\Scripts\activate
# Dấu nhắc sẽ đổi thành: (.venv) PS D:\project\transcript meeting>

# Cài tất cả thư viện (~vài phút, tải ~2 GB)
pip install -r requirements.txt
```

**Các thư viện chính sẽ được cài:**

```
faster-whisper    — nhận dạng giọng nói (Whisper large-v3)
pyannote.audio    — phân tách người nói
torch             — PyTorch (CPU hoặc CUDA)
gradio            — web UI
sounddevice       — ghi âm
imageio-ffmpeg    — xử lý audio/video (kèm ffmpeg binary)
requests          — gọi Ollama API
python-dotenv     — đọc file .env
```

> ⚠️ Nếu gặp lỗi liên quan đến Microsoft C++ Build Tools:
> ```powershell
> # Cài build tools (miễn phí)
> winget install Microsoft.VisualStudio.2022.BuildTools
> # Rồi cài lại requirements
> pip install -r requirements.txt
> ```

---

## 4. Cấu hình HuggingFace Token

Token này cần để tải model **pyannote.audio** (phân tách người nói). Miễn phí.

### Bước 4.1 — Đăng ký HuggingFace

Vào https://huggingface.co → **Sign Up** → xác nhận email.

### Bước 4.2 — Chấp nhận điều khoản 2 model

Phải làm **cả hai**, nếu không pyannote sẽ báo lỗi 403:

```
→ https://huggingface.co/pyannote/speaker-diarization-3.1
  Click "Agree and access repository"

→ https://huggingface.co/pyannote/segmentation-3.0
  Click "Agree and access repository"
```

### Bước 4.3 — Tạo Access Token

1. Vào https://huggingface.co/settings/tokens
2. Click **"New token"**
3. Đặt tên: `meeting-transcriber`
4. Loại: **Read** (không cần Write)
5. Click **Generate** → copy token (bắt đầu bằng `hf_...`)

### Bước 4.4 — Lưu vào .env

```powershell
# Trong thư mục project
copy .env.example .env

# Mở bằng Notepad
notepad .env
```

Sửa dòng:
```env
HF_TOKEN=hf_xxxxxxxx  →  HF_TOKEN=hf_AbCdEf123456...   (token thật của bạn)
```

Lưu file (Ctrl+S) và đóng Notepad.

---

## 5. Cài VB-CABLE để ghi âm hệ thống (Zoom / Teams / Meet)

VB-CABLE là virtual audio driver miễn phí — tạo ra một cặp thiết bị ảo (CABLE Input + CABLE Output) để "bắt" âm thanh từ hệ thống.

### Bước 5.1 — Tải và cài VB-CABLE

1. Vào https://vb-audio.com/Cable/
2. Click **"Download VB-CABLE Driver"** (miễn phí, tác giả khuyến khích donate)
3. Giải nén file `.zip`
4. Chuột phải `VBCABLE_Setup_x64.exe` → **Run as administrator**
5. Click **"Install Driver"**
6. **Khởi động lại máy** (bắt buộc để driver có hiệu lực)

### Bước 5.2 — Chọn cách cấu hình âm thanh

#### Cách A — Chỉ ghi, không nghe (đơn giản nhất)

```
1. Chuột phải icon 🔊 ở Taskbar → "Sound settings"
   hoặc Win+I → System → Sound

2. Phần "Output" → chọn "CABLE Input (VB-Audio Virtual Cable)"
```

```
Zoom/Teams ──► CABLE Input ──► CABLE Output ──► App ghi lại
                    ↑
              (bạn chọn cái này làm output)
```

> ⚠️ Bạn sẽ **không nghe** âm thanh qua loa trong thời gian ghi.  
> Sau cuộc họp, nhớ đổi lại loa thật.

#### Cách B — Vừa ghi vừa nghe (khuyến nghị)

```
1. Nhấn Win+R → gõ "mmsys.cpl" → Enter
   (mở cửa sổ Sound cũ)

2. Tab "Recording"
   → Tìm "CABLE Output (VB-Audio Virtual Cable)"
   → Chuột phải → "Properties"

3. Tab "Listen"
   → Tích "Listen to this device"
   → "Playback through this device": chọn loa/tai nghe thật của bạn
   → OK

4. Tab "Playback"
   → Chuột phải "CABLE Input" → "Set as Default Device"
```

```
Zoom/Teams ──► CABLE Input ──► CABLE Output ──┬──► App ghi lại
                                               │
                                               └──► Loa/Tai nghe (bạn nghe)
```

> ✅ Bây giờ bạn vừa nghe vừa ghi được!

### Bước 5.3 — Trong app

Ở tab **Đầu vào** → Chế độ ghi âm → Chọn thiết bị: **CABLE Output (VB-Audio Virtual Cable)**

---

## 6. Tăng tốc với NVIDIA GPU (tùy chọn)

Nếu bạn có GPU NVIDIA (≥ 4GB VRAM), bạn có thể tăng tốc Whisper và pyannote lên **5–10×**.

### Bước 6.1 — Kiểm tra GPU

```powershell
nvidia-smi
# → Hiển thị tên GPU và driver version
```

Nếu lệnh không tìm thấy, tải driver tại https://www.nvidia.com/Download/index.aspx.

### Bước 6.2 — Cài PyTorch với CUDA

```powershell
# Trong môi trường .venv đã kích hoạt
# Gỡ PyTorch CPU (đã cài)
pip uninstall torch torchaudio -y

# Cài PyTorch với CUDA 12.1
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

# Kiểm tra CUDA hoạt động
python -c "import torch; print('CUDA:', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0))"
# → CUDA: True | NVIDIA GeForce RTX ...
```

### Bước 6.3 — Cài CTranslate2 với CUDA (cho faster-whisper)

```powershell
pip install ctranslate2 --extra-index-url https://pypi.nvidia.com
```

Sau đó, app sẽ tự phát hiện CUDA và dùng GPU khi chạy. Log sẽ hiển thị:
```
INFO — Using device=cuda, compute_type=int8_float16
```

---

## 7. Chạy app lần đầu

```powershell
# Kích hoạt môi trường ảo (nếu chưa)
.venv\Scripts\activate

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

> 🕐 **Lần đầu chạy:** Whisper (~3GB) và pyannote (~1GB) sẽ tự tải về  
> `C:\Users\<tên>\\.cache\huggingface\`  
> Từ lần 2 trở đi, load từ cache — chỉ mất vài giây.

---

## 8. Kiểm tra nhanh

```powershell
# Trong môi trường .venv đã kích hoạt
pytest tests/test_pipeline.py::TestAlign -v
pytest tests/test_pipeline.py::TestConvert -v
pytest tests/test_pipeline.py::TestConfig -v
```

Kết quả mong đợi:
```
tests/test_pipeline.py::TestAlign::test_align_merge_basic          PASSED
tests/test_pipeline.py::TestAlign::test_align_merge_no_turns       PASSED
tests/test_pipeline.py::TestAlign::test_align_to_text_format       PASSED
tests/test_pipeline.py::TestAlign::test_collapse_consecutive_speakers PASSED
tests/test_pipeline.py::TestConvert::test_ffmpeg_available         PASSED
tests/test_pipeline.py::TestConfig::test_config_loads              PASSED
```

---

## 9. Troubleshooting

### ❌ `python` không nhận dạng được / `'python' is not recognized`

Python chưa được thêm vào PATH. Giải pháp:

```powershell
# Tìm Python đã cài
where python

# Nếu không tìm thấy → cài lại Python, nhớ tích "Add to PATH"
# Hoặc thêm thủ công vào Environment Variables:
# Win+S → "Environment Variables" → Path → New → C:\Users\<bạn>\AppData\Local\Programs\Python\Python311
```

---

### ❌ `ollama: command not found` trong PowerShell

Ollama chưa được thêm vào PATH hoặc chưa cài xong. Thử:

```powershell
# Kiểm tra Ollama đang chạy
Get-Process ollama -ErrorAction SilentlyContinue

# Kiểm tra qua HTTP
Invoke-WebRequest http://localhost:11434 -UseBasicParsing
# → StatusCode: 200 ← OK
```

Nếu Ollama không chạy:
```powershell
# Tìm và chạy thủ công
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve
```

---

### ❌ `pip install` lỗi — Microsoft Visual C++ required

```powershell
# Cài Visual C++ Build Tools
winget install Microsoft.VisualStudio.2022.BuildTools --override "--add Microsoft.VisualStudio.Workload.VCTools"
# Restart PowerShell và thử lại pip install
```

---

### ❌ `401` hoặc `403` khi tải pyannote model

- Kiểm tra `HF_TOKEN` trong `.env` đúng chưa (copy đúng, không thừa dấu cách)
- Xác nhận đã accept terms **cả 2 model**:
  - https://huggingface.co/pyannote/speaker-diarization-3.1
  - https://huggingface.co/pyannote/segmentation-3.0

---

### ❌ Không nghe âm thanh sau khi cài VB-CABLE

Kiểm tra cấu hình "Listen to this device" (Cách B):
```
Win+R → mmsys.cpl → Recording → CABLE Output → Properties → Listen
→ Đảm bảo tích "Listen to this device"
→ Playback through: chọn đúng loa/tai nghe thật
```

---

### ❌ App ghi âm nhưng transcript toàn im lặng

1. Kiểm tra **CABLE Input** đã được đặt làm Default Playback chưa:
   ```
   Win+R → mmsys.cpl → Playback → CABLE Input → "Set as Default"
   ```
2. Mở **Volume Mixer** (chuột phải icon loa → Open Volume Mixer) → đảm bảo ứng dụng họp không bị mute
3. Ghi 10 giây → mở file WAV trong Windows Media Player để kiểm tra

---

### ❌ `sounddevice.PortAudioError: [Errno -9996] Invalid device`

Thiết bị ghi âm không hợp lệ. Trong app, thử chọn thiết bị khác từ dropdown.  
Hoặc kiểm tra danh sách thiết bị:
```python
import sounddevice as sd
print(sd.query_devices())
```

---

### ❌ Transcribe chậm / máy đứng

- Đóng Chrome/Edge và các tab nhiều RAM trước khi xử lý
- Dùng model nhỏ hơn: trong `.env` đặt `WHISPER_MODEL=medium`
- Nếu có NVIDIA GPU: làm theo [Bước 6](#6-tăng-tốc-với-nvidia-gpu-tùy-chọn)
- Task Manager → xem CPU/RAM đang dùng bao nhiêu %

---

### 🔄 Reset hoàn toàn môi trường

```powershell
# Xóa venv cũ
Remove-Item -Recurse -Force .venv

# Tạo lại từ đầu
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Mẹo sử dụng hàng ngày

```powershell
# Tạo shortcut để chạy nhanh — lưu vào file run.bat:
@echo off
cd /d "D:\project\transcript meeting"
call .venv\Scripts\activate
python app.py
pause
```

Double-click `run.bat` để mở app mà không cần mở PowerShell.
