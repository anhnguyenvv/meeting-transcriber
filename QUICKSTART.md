# 🚀 Hướng dẫn cài đặt nhanh

> Dành cho người không rành lập trình.  
> Bạn chỉ cần **làm theo từng bước**, không cần hiểu kỹ thuật.

---

## Trước khi bắt đầu — cần gì?

| Thứ cần | Ở đâu | Ghi chú |
|---|---|---|
| 💻 Máy tính | Windows 11 hoặc MacBook | RAM ≥ 8 GB khuyến nghị |
| 🌐 Internet | Kết nối ổn định | Chỉ cần khi tải phần mềm lần đầu |
| ⏰ Thời gian | ~30 phút | Chủ yếu chờ tải |

---

## Cài đặt — chỉ 2 bước chính

---

### 🪟 Nếu bạn dùng Windows 11

**Bước 1 — Tải về 2 phần mềm này:**

> **Python** — ngôn ngữ lập trình (bộ máy chạy app)  
> 👉 https://www.python.org/downloads/  
> → Click nút vàng **"Download Python 3.11.x"**  
> → Chạy file tải về  
> → **QUAN TRỌNG:** Tích ô **"Add Python to PATH"** trước khi nhấn Install

> **Ollama** — phần mềm chạy AI trên máy  
> 👉 https://ollama.com/download  
> → Click **"Download for Windows"**  
> → Chạy file tải về, cài như phần mềm bình thường

**Bước 2 — Chạy file cài đặt tự động:**

```
Vào thư mục "transcript meeting"
→ Double-click vào file  install.bat
→ Làm theo hướng dẫn trên màn hình
→ Đợi tải xong (10–20 phút tùy tốc độ mạng)
```

![Windows installer](https://i.imgur.com/placeholder-windows.png)

Sau khi cài xong, sẽ có file **"Meeting Transcriber.bat"** trên Desktop.  
Mỗi lần dùng: **double-click vào đó** là xong!

---

### 🍎 Nếu bạn dùng MacBook (Apple Silicon)

**Bước 1 — Mở Terminal:**
- Nhấn `Cmd + Space` → gõ **Terminal** → Enter

**Bước 2 — Copy và paste lệnh này vào Terminal, nhấn Enter:**

```bash
bash "/path/to/transcript meeting/install.sh"
```

*(Thay `/path/to/` bằng đường dẫn thực tế đến thư mục)*

Hoặc đơn giản hơn: kéo thả file `install.sh` vào Terminal, rồi nhấn Enter.

Làm theo hướng dẫn trên màn hình (có thể hỏi mật khẩu macOS — bình thường).

---

## Trong lúc cài — Wizard sẽ hỏi bạn 2 câu

### Câu 1: Chọn kích thước model

```
  Máy bạn bao nhiêu RAM?

  ► 1. Nhỏ (tiết kiệm RAM)   — RAM 4-6 GB   — Tải ~1.5 GB
    2. Vừa (khuyến nghị)     — RAM 8 GB     — Tải ~2.4 GB  ← Hầu hết laptop chọn cái này
    3. Lớn (chất lượng cao)  — RAM 16+ GB   — Tải ~6.2 GB
```

**Không biết RAM máy mình bao nhiêu?**
- Windows: Nhấn `Win + I` → System → About → "Installed RAM"
- Mac: Apple menu  → About This Mac → xem "Memory"

### Câu 2: HuggingFace Token (tùy chọn)

```
  Bạn có muốn cài HuggingFace token không?
  (Token này dùng để nhận biết ai đang nói)

  → Nhấn N để bỏ qua (app vẫn chạy, chỉ không biết ai nói)
  → Nhấn Y nếu muốn cài (cần tạo tài khoản miễn phí)
```

**Nếu chọn Y — làm theo wizard hướng dẫn:**
1. Vào https://huggingface.co → đăng ký (giống đăng ký email)
2. Chấp nhận điều khoản tại 2 link (wizard sẽ hiển thị)
3. Tạo token → copy → dán vào wizard

---

## Sau khi cài xong — cách sử dụng

### Mở app

- **Windows:** Double-click **"Meeting Transcriber.bat"** trên Desktop
- **Mac:** Double-click **"Meeting Transcriber.command"** trên Desktop
- Sau đó mở trình duyệt vào: **http://localhost:7860**

### Dùng app (3 bước)

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  BƯỚC 1 — Chọn file hoặc ghi âm                                │
│  ┌──────────────────────────────────────────┐                  │
│  │  📁 Kéo thả file MP3/MP4/WAV vào đây    │                  │
│  │      hoặc click để chọn file            │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                 │
│  BƯỚC 2 — Điền tên cuộc họp (tùy chọn)                        │
│  [ Sprint Review tháng 5              ]                         │
│                                                                 │
│  BƯỚC 3 — Nhấn nút Xử lý                                       │
│  [         🚀 Xử lý          ]                                 │
│                                                                 │
│  → Đợi vài phút (thanh tiến trình sẽ hiện)                    │
│  → Xem kết quả ở 2 tab bên dưới                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Xem kết quả

Sau khi xử lý xong, click vào các tab:

| Tab | Nội dung |
|---|---|
| **📄 Transcript** | Xem và tải bản gốc (trái) + bản dịch tiếng Việt (phải) |
| **📋 Tóm tắt** | Tóm tắt cuộc họp bằng tiếng Việt, có thể tải về |

File kết quả cũng được lưu tự động trong thư mục **`outputs/`**.

---

## Ghi âm cuộc họp trực tiếp (Zoom/Teams/Meet)

Cần cài thêm driver âm thanh ảo để ghi tiếng phát ra từ máy tính:

### Windows: VB-CABLE
1. Vào https://vb-audio.com/Cable/ → Download
2. Giải nén → chuột phải `VBCABLE_Setup_x64.exe` → **Run as administrator**
3. **Khởi động lại máy**
4. Sau đó trong app: chọn chế độ **"Ghi âm"** → chọn thiết bị **"CABLE Output"**

### Mac: BlackHole
```bash
# Chạy lệnh này trong Terminal
brew install blackhole-2ch
```
Xem hướng dẫn cài Multi-Output Device chi tiết trong [docs/setup-macos.md](docs/setup-macos.md).

---

## Câu hỏi thường gặp

**❓ App chạy chậm / máy nóng**  
→ Bình thường! AI cần CPU mạnh. File 30 phút sẽ xử lý trong 15–30 phút.  
→ Nếu muốn nhanh hơn: mở app → chọn lại model "Nhỏ" trong `.env`

**❓ Lỗi "Cannot connect to Ollama"**  
→ Ollama chưa chạy. Mở Terminal/PowerShell và gõ: `ollama serve`

**❓ Transcript sai nhiều / không nhận ra tiếng Nhật**  
→ Chọn model lớn hơn trong wizard (cần RAM ≥ 16GB)  
→ Hoặc đảm bảo file âm thanh rõ, không nhiều tiếng ồn

**❓ Không có nhãn Speaker 1, Speaker 2**  
→ Chưa cài HF token. Chạy lại `python setup_wizard.py` và chọn Y ở câu hỏi token

**❓ Muốn xóa app / gỡ cài đặt**  
→ Xóa thư mục `transcript meeting` là xong  
→ Xóa model Ollama: `ollama rm qwen2.5:3b`  
→ Xóa model Whisper: xóa thư mục `~/.cache/huggingface/`

**❓ Lần sau chạy app có phải tải model lại không?**  
→ Không! Model chỉ tải 1 lần. Lần sau chạy gần như ngay lập tức.

---

## Cần hỗ trợ?

Xem hướng dẫn chi tiết hơn tại:
- 🪟 Windows: [docs/setup-windows.md](docs/setup-windows.md)
- 🍎 Mac: [docs/setup-macos.md](docs/setup-macos.md)
- 📖 Tài liệu đầy đủ: [README.md](README.md)
