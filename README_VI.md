# 🎙️ Meeting Transcriber

Ứng dụng **Meeting Transcriber** là một công cụ bóc băng cuộc họp và xử lý âm thanh thời gian thực, hoạt động hoàn toàn **offline/local** trên máy tính của bạn để đảm bảo quyền riêng tư tuyệt đối.

Dự án kết hợp sức mạnh của các mô hình AI tiên tiến:
- **Faster-Whisper**: Nhận diện giọng nói (Speech-to-Text) tốc độ cao và chính xác.
- **Pyannote Audio**: Phân tách người nói (Speaker Diarization - nhận biết ai đang nói).
- **Qwen2.5 (Ollama)**: Dịch thuật, chuẩn hóa văn bản và tóm tắt nội dung cuộc họp bằng LLM.

## 🚀 Tính năng nổi bật

1. **Bóc băng đa ngôn ngữ**: Hỗ trợ nhận diện giọng nói cực tốt với Tiếng Việt, Tiếng Anh, Tiếng Nhật, v.v.
2. **Phân tách người nói (Diarization)**: Tự động gán nhãn "Speaker 1", "Speaker 2" cho từng đoạn hội thoại.
3. **Tóm tắt cuộc họp bằng AI**: Tự động tạo bản tóm tắt, trích xuất công việc (Action Items) qua giao tiếp với Ollama.
4. **Thu âm trực tiếp (Live Capture)**: Ghi âm song song từ Micro và Âm thanh hệ thống (Loa máy tính), tích hợp bộ trộn thông minh (Smart Ducking) chống vang tiếng.
5. **Giao diện trực quan**: Xây dựng trên nền tảng Gradio thân thiện, dễ sử dụng.

---

### Khuyến nghị

| Thành phần | Khuyến nghị |
|---|---|
| **RAM** | 16 GB — chạy song song Whisper + pyannote thoải mái |
| **GPU (Windows)** | NVIDIA ≥ 6GB VRAM → tăng tốc Whisper + pyannote (CUDA) |
| **Apple Silicon** | M1 Pro/Max/Ultra hoặc M2+ — CPU SIMD đủ mạnh cho int8 |
| **Đĩa** | SSD (HDD sẽ chậm khi load model lần đầu) |

### Ước tính thời gian xử lý (file 30 phút)

| Bước | Apple M2 (CPU) | Windows i7 (CPU) | Windows + RTX 3060 |
|---|---|---|---|
| Convert audio | ~5 giây | ~5 giây | ~5 giây |
| Transcribe (Whisper large-v3) | ~8 phút | ~15 phút | ~2 phút |
| Diarize (pyannote) | ~4 phút | ~8 phút | ~1 phút |
| Translate (Qwen2.5 7B) | ~2 phút | ~3 phút | ~2 phút |
| Summarize (Qwen2.5 7B) | ~1 phút | ~2 phút | ~1 phút |
| **Tổng** | **~15 phút** | **~28 phút** | **~6 phút** |

> 💡 Dùng `WHISPER_MODEL=medium` trong `.env` để tăng tốc ~2× (hy sinh chút độ chính xác).

---
## 🏗️ Kiến trúc hệ thống & Tài liệu kỹ thuật

Để xem thông tin chi tiết về kiến trúc hệ thống, luồng dữ liệu, các quyết định công nghệ và cách xử lý các thách thức kỹ thuật (như Smart Ducking, đồng bộ thời gian), vui lòng tham khảo tài liệu chi tiết:

👉 **[Tài liệu Kiến trúc hệ thống (Tiếng Anh)](docs/architecture.md)**

---


## ⚡ Cài đặt nhanh

### macOS (Apple Silicon)

```bash
# 1. Cài Homebrew nếu chưa có
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Cài Python, Ollama, BlackHole
brew install python@3.11 ollama blackhole-2ch

# 3. Kéo LLM model (~5 GB)
ollama pull qwen2.5:3b-instruct

# 4. Tạo môi trường Python và cài dependencies
cd "/path/to/transcript meeting"
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 5. Cấu hình
cp .env.example .env
# → Mở .env, điền HF_TOKEN (xem mục "Lấy HF Token" bên dưới)

# 6. Chạy!
python app.py
```

### Windows 11

```powershell
# (Chạy PowerShell với quyền thường — không cần Admin)

# 1. Cài Python 3.11 từ https://www.python.org → tích "Add to PATH"
# 2. Cài Ollama từ https://ollama.com/download

# 3. Kéo LLM model (~5 GB)
ollama pull qwen2.5:7b-instruct

# 4. Tạo môi trường Python và cài dependencies
cd "D:\project\transcript meeting"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 5. Cấu hình
copy .env.example .env
# → Mở .env bằng Notepad, điền HF_TOKEN

# 6. Chạy!
python app.py
```

---

## 📖 Hướng dẫn chi tiết

- **macOS:** [docs/setup-macos.md](docs/setup-macos.md) — BlackHole, Multi-Output Device, troubleshooting
- **Windows:** [docs/setup-windows.md](docs/setup-windows.md) — VB-CABLE, cấu hình âm thanh, troubleshooting

---

## ⚙️ Cấu hình

Toàn bộ cấu hình nằm trong file **`.env`** (copy từ `.env.example`):

```env
# ── Bắt buộc ─────────────────────────────────────────────────
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── Tùy chọn (có giá trị mặc định) ──────────────────────────
WHISPER_MODEL=large-v3       # tiny | base | small | medium | large-v3
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
```

### Chọn kích thước Whisper model

| Model | Kích thước | Tốc độ | Độ chính xác |
|---|---|---|---|
| `tiny` | 75 MB | ⚡⚡⚡⚡⚡ | ★★☆☆☆ |
| `base` | 145 MB | ⚡⚡⚡⚡ | ★★★☆☆ |
| `small` | 466 MB | ⚡⚡⚡ | ★★★☆☆ |
| `medium` | 1.5 GB | ⚡⚡ | ★★★★☆ |
| `large-v3` | 3.1 GB | ⚡ | ★★★★★ ← **mặc định** |

> Với tiếng Nhật và tiếng Việt có giọng địa phương, `large-v3` cho kết quả tốt hơn rõ rệt.

### Lấy HuggingFace Token

```
1. Đăng ký tại:   https://huggingface.co  (miễn phí)

2. Accept terms của 2 model sau (BẮT BUỘC):
   → https://huggingface.co/pyannote/speaker-diarization-3.1
   → https://huggingface.co/pyannote/segmentation-3.0

3. Tạo token tại: https://huggingface.co/settings/tokens
   Chọn loại: Read (không cần Write)

4. Thêm vào .env:
   HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚡ **Không muốn đăng ký?** Tích **"Bỏ qua phân tách người nói"** trong UI.  
> App vẫn chạy đầy đủ — transcript, dịch, tóm tắt — chỉ không có nhãn Speaker 1/2/…

---

## 🖥️ Sử dụng

### Khởi động

```bash
# macOS
source .venv/bin/activate && python app.py

# Windows
.venv\Scripts\activate; python app.py
```

Mở trình duyệt tại **http://localhost:7860**

---

### Tab 1 — Đầu vào

```
┌─────────────────────────────────────────────┐
│  Chế độ: ● Tải file  ○ Ghi âm              │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  Kéo thả file vào đây               │   │
│  │  hoặc click để chọn                 │   │
│  │  (mp3, wav, mp4, m4a, ogg…)         │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  Tên cuộc họp: [Sprint Review Q2      ]    │
│  Số người nói: [2                     ]    │
│  □ Bỏ qua phân tách người nói              │
│                                             │
│  [        🚀 Xử lý        ]               │
└─────────────────────────────────────────────┘
```

**Chế độ ghi âm:**
- Chọn thiết bị mic hoặc loopback (BlackHole/VB-CABLE)
- Nhấn **🔴 Bắt đầu ghi** → bắt đầu cuộc họp
- Nhấn **⏹️ Dừng ghi** → tự động xử lý

---

### Tab 2 — Transcript

Hiển thị song song:

| Bên trái — Bản gốc | Bên phải — Tiếng Việt |
|---|---|
| Ngôn ngữ gốc (JA/EN/VI) | Bản dịch tiếng Việt |
| Có nhãn Speaker + timestamp | Giữ nguyên nhãn + timestamp |
| Nút tải `.txt` | Nút tải `.txt` |

---

### Tab 3 — Tóm tắt

Hiển thị tóm tắt Markdown tiếng Việt có cấu trúc:
- Bối cảnh
- Các điểm chính (bullets)
- Quyết định
- Hành động cần thực hiện (bảng: ai · việc gì · khi nào)
- Câu hỏi còn mở

Nút tải file `.md` để dùng trong Notion/Obsidian/Word.

---

## 📁 Cấu trúc đầu ra

```
outputs/
└─ 20260509_143022__Sprint_Review_Q2/
   ├─ transcript_original.txt    ← Transcript gốc, speaker-labelled
   ├─ transcript_original.srt    ← Phụ đề SRT (dùng được với VLC, Premiere…)
   ├─ transcript_vi.txt          ← Bản dịch tiếng Việt
   ├─ summary_vi.md              ← Tóm tắt Markdown tiếng Việt
   └─ metadata.json              ← Thông tin: ngôn ngữ, thời lượng, model
```

**metadata.json mẫu:**
```json
{
  "title": "Sprint Review Q2",
  "language": "ja",
  "duration_s": 1842.5,
  "speaker_count": 3,
  "segment_count": 187,
  "whisper_model": "large-v3",
  "diarization_model": "pyannote/speaker-diarization-3.1",
  "ollama_model": "qwen2.5:7b-instruct",
  "created_at": "20260509_143022"
}
```

---

## 🗂️ Cấu trúc source code

```
transcript meeting/
│
├─ app.py                   ← Gradio UI, entry point (python app.py)
├─ requirements.txt
├─ .env.example             ← Template cấu hình
├─ .gitignore
├─ README.md                ← Tài liệu này
│
├─ src/
│  ├─ config.py             ← Load .env, OS detection, constants
│  ├─ ollama_client.py      ← HTTP client cho Ollama API (chat, health check)
│  ├─ transcribe.py         ← Wrapper faster-whisper → List[TranscriptSegment]
│  ├─ diarize.py            ← Wrapper pyannote → List[SpeakerTurn]
│  ├─ align.py              ← Ghép segments + turns → List[AlignedLine]
│  ├─ translate.py          ← Dịch sang VI (chunk + stitch)
│  ├─ summarize.py          ← Tóm tắt VI (structured prompt)
│  ├─ pipeline.py           ← Orchestrator: convert→transcribe→diarize
│  │                                         →align→translate→summarize→save
│  └─ audio/
│     ├─ devices.py         ← Liệt kê thiết bị âm thanh (mic/loopback)
│     ├─ recorder.py        ← Ghi âm live (AudioRecorder class)
│     └─ convert.py         ← FFmpeg: any format → 16kHz mono WAV
│
├─ docs/
│  ├─ setup-macos.md        ← Hướng dẫn macOS (BlackHole, Multi-Output)
│  └─ setup-windows.md      ← Hướng dẫn Windows (VB-CABLE)
│
├─ outputs/                 ← Kết quả xử lý (gitignored)
│  └─ YYYYMMDD_HHMMSS__title/
│
└─ tests/
   ├─ test_pipeline.py      ← Unit tests (align) + integration tests
   └─ samples/              ← Đặt file WAV mẫu vào đây để test
```

---

## ❓ Câu hỏi thường gặp

**Q: App có gửi dữ liệu lên cloud không?**  
A: Không. Whisper, pyannote và Ollama đều chạy hoàn toàn local. Dữ liệu họp không rời khỏi máy tính của bạn.

**Q: Model tải về lưu ở đâu?**  
A: Whisper và pyannote → `~/.cache/huggingface/` · Ollama → `~/.ollama/models/`

**Q: Lần sau chạy có phải tải lại không?**  
A: Không. Model chỉ tải lần đầu. Lần sau load từ cache, mất vài giây.

**Q: Không có GPU NVIDIA thì sao?**  
A: App vẫn chạy tốt trên CPU. Apple Silicon (M1/M2/M3) đặc biệt hiệu quả nhờ unified memory.

**Q: Có thể dùng model Ollama khác không?**  
A: Có. Thay `OLLAMA_MODEL` trong `.env`. Bất kỳ model nào hỗ trợ tiếng Việt + Nhật đều được.  
Ví dụ: `qwen2.5:14b-instruct` (chất lượng cao hơn, ~8GB) hoặc `llama3.1:8b` (tiếng Anh tốt hơn).

**Q: File meeting bị lỗi hoặc chất lượng âm thanh xấu thì sao?**  
A: App tự convert mọi định dạng qua FFmpeg. Âm thanh xấu (nhiều tiếng ồn, giọng nhỏ) sẽ làm giảm độ chính xác Whisper — nên dùng headset khi họp hoặc dùng noise cancellation.

**Q: Cuộc họp code-switch (vừa Nhật vừa Anh) có nhận dạng được không?**  
A: Whisper phát hiện ngôn ngữ **theo file**, không theo từng câu. Nếu file chứa nhiều ngôn ngữ, nó sẽ chọn ngôn ngữ chiếm đa số và vẫn cố nhận dạng phần còn lại. Kết quả có thể không hoàn hảo với code-switching nặng.

**Q: Có thể đổi tên Speaker 1/2 thành tên thật không?**  
A: Hiện tại chưa có trong UI. Bạn có thể dùng Find & Replace trong file `.txt` sau khi xuất.  
Tính năng đặt tên người nói sẽ có trong phiên bản tiếp theo.

**Q: Chạy trên Linux được không?**  
A: Về lý thuyết có (tất cả thư viện hỗ trợ Linux). Tuy nhiên chưa được test chính thức.  
Xem `docs/` để tham khảo — thay BlackHole/VB-CABLE bằng PulseAudio `pavucontrol`.

---

## 📄 Giấy phép

Dự án này: **MIT License**

Các model và thư viện bên thứ ba có giấy phép riêng:

| Thành phần | Giấy phép |
|---|---|
| OpenAI Whisper | MIT |
| faster-whisper | MIT |
| pyannote.audio | MIT (model cần accept terms riêng) |
| Qwen2.5 | Qianwen License (cho phép dùng cá nhân/thương mại) |
| Ollama | MIT |
| Gradio | Apache 2.0 |
