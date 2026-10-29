"""
app.py — Gradio web UI for the multilingual meeting transcriber.

Features:
  - Upload file / Record mode (batch processing)
  - Live transcription mode (real-time mic + system audio capture)
  - Per-chunk multilingual language detection (JA / EN / VI)
  - Translation to Vietnamese + AI summary via Ollama

Run with:
    python app.py
Then open http://localhost:7860 in your browser.
"""
from __future__ import annotations

import logging
import threading
import time
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
import gradio as gr

from fastapi import FastAPI, Request, Form, Query
import uvicorn
import subprocess

from src.audio.devices import device_names, device_by_label, find_loopback_device
from src.audio.recorder import AudioRecorder
from src.config import IS_MAC, IS_WIN, LIVE_CHUNK_DURATION_S, SAMPLE_RATE
from src.ollama_client import is_ollama_available
from src import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

# ── Global recorder state ─────────────────────────────────────────────────────
_recorder: Optional[AudioRecorder] = None
_recorder_lock = threading.Lock()

# ── Global live session state ─────────────────────────────────────────────────
_live_capture = None
_live_transcriber = None
_live_thread: Optional[threading.Thread] = None
_last_poll_time: float = 0.0
_live_lock = threading.Lock()

# ── Global browser live session state ─────────────────────────────────────────
_browser_audio_chunks = []
_browser_live_transcriber = None
_browser_live_lock = threading.Lock()
_browser_live_title = "live_meeting"
_browser_live_out_dir = None

# ── FastAPI Application & Endpoints ───────────────────────────────────────────
fastapi_app = FastAPI()

@fastapi_app.post("/api/live/start")
async def api_live_start(title: str = Form("live_meeting"), force_language: str = Form(None)):
    global _browser_live_transcriber, _browser_audio_chunks, _browser_live_title
    with _browser_live_lock:
        if _browser_live_transcriber and _browser_live_transcriber.is_running:
            return {"status": "error", "message": "Phiên live đang chạy!"}
        
        from src.live_transcribe import LiveTranscriber
        _browser_live_title = title or "live_meeting"
        lang = force_language if force_language and force_language != "Auto" else None
        _browser_live_transcriber = LiveTranscriber(
            title=_browser_live_title,
            force_language=lang
        )
        _browser_live_transcriber.start()
        _browser_audio_chunks = []
        logger.info("API: Live browser session started - Title: %s, Lang: %s", _browser_live_title, lang)
    return {"status": "success"}

@fastapi_app.post("/api/live/chunk")
async def api_live_chunk(request: Request, offset_s: float = Query(...)):
    global _browser_live_transcriber, _browser_audio_chunks
    body = await request.body()
    if len(body) == 0:
        return {"status": "success", "message": "Empty chunk"}
    
    # Bytes to float32 numpy array
    audio_np = np.frombuffer(body, dtype=np.float32)
    
    with _browser_live_lock:
        if _browser_live_transcriber and _browser_live_transcriber.is_running:
            _browser_audio_chunks.append(audio_np.copy())
            _browser_live_transcriber.process_chunk(audio_np, offset_s)
    return {"status": "success"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _loopback_hint_md() -> str:
    if IS_MAC:
        return (
            "**macOS:** Cài [BlackHole 2ch](https://existential.audio/blackhole/) rồi tạo "
            "**Multi-Output Device** trong *Audio MIDI Setup* kết hợp loa + BlackHole. "
            "Đặt Multi-Output là đầu ra hệ thống khi họp."
        )
    elif IS_WIN:
        return (
            "**Windows:** Cài [VB-CABLE](https://vb-audio.com/Cable/). Trong *Sound Settings* → "
            "chọn **CABLE Input** làm loa mặc định (hoặc dùng 'Listen to this device')."
        )
    return "Xem `docs/setup-macos.md` hoặc `docs/setup-windows.md` để cài loopback driver."


# ── Process function (batch) ──────────────────────────────────────────────────

def process(
    input_mode: str,
    uploaded_file,
    device_label: str,
    title: str,
    num_speakers_str: str,
    skip_diarization: bool,
    progress: gr.Progress = gr.Progress(track_tqdm=False),
):
    """Main processing callback — called when user clicks 'Xử lý'."""

    # Resolve audio path
    if input_mode == "📁 Tải file lên":
        if uploaded_file is None:
            return (
                "❌ Chưa chọn file.",
                "", "", "", None, None, None,
            )
        audio_path = Path(uploaded_file)
    else:
        return (
            "❌ Để dùng chế độ ghi âm, nhấn **Bắt đầu ghi** trước, rồi **Dừng ghi** để lấy file.",
            "", "", "", None, None, None,
        )

    # Parse num_speakers
    num_speakers = None
    if num_speakers_str.strip().isdigit():
        num_speakers = int(num_speakers_str.strip())
        if num_speakers < 1:
            num_speakers = None

    log_lines: list[str] = []

    def cb(msg: str):
        log_lines.append(msg)
        progress(0, desc=msg)

    try:
        result = pipeline.run(
            audio_path=audio_path,
            title=title or audio_path.stem,
            num_speakers=num_speakers,
            skip_diarization=skip_diarization,
            progress_cb=cb,
        )
    except Exception as e:
        logger.exception("Pipeline error")
        return (
            f"❌ Lỗi: {e}",
            "", "", "", None, None, None,
        )

    status = (
        f"✅ Hoàn thành! Ngôn ngữ: **{result.language}** | "
        f"Người nói: **{result.speaker_count}** | "
        f"Thời lượng: **{result.duration_s/60:.1f} phút** | "
        f"Lưu tại: `{result.output_dir}`"
    )

    orig_file = str(result.output_dir / "transcript_original.txt")
    vi_file   = str(result.output_dir / "transcript_vi.txt")
    sum_file  = str(result.output_dir / "summary_vi.md")

    return (
        status,
        result.transcript_original,
        result.transcript_vi,
        result.summary_vi,
        orig_file,
        vi_file,
        sum_file,
    )


# ── Recording callbacks (batch) ──────────────────────────────────────────────

def start_recording(device_label: str) -> tuple[str, str]:
    global _recorder
    with _recorder_lock:
        if _recorder and _recorder.is_recording:
            return "⚠️ Đang ghi rồi!", gr.update()

        device = device_by_label(device_label) if device_label else None
        _recorder = AudioRecorder(device_index=device.index if device else None)
        _recorder.start()
        return "🔴 Đang ghi âm …", gr.update()


def stop_recording() -> tuple[str, str]:
    global _recorder
    with _recorder_lock:
        if _recorder is None or not _recorder.is_recording:
            return "⚠️ Không có phiên ghi nào đang chạy.", gr.update()
        wav_path = _recorder.stop()
        _recorder = None
        return f"✅ Đã lưu: {wav_path.name}", str(wav_path)


def _render_interactive_transcript(updates: list, audio_elem_id: str) -> str:
    """Render transcript updates as clickable HTML to seek audio."""
    if not updates:
        return "<div style='padding: 10px; color: #666;'>Chưa có dữ liệu...</div>"
        
    html = f"<div id='{audio_elem_id}_container' style='line-height: 1.6; font-size: 1.1em; max-height: 400px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 8px; background: #fff;'>"
    for u in updates:
        start = getattr(u, 'timestamp_s', 0)
        text = getattr(u, 'text', '')
        if not text.strip(): continue
        
        em, es = divmod(int(start), 60)
        ts_str = f"[{em:02d}:{es:02d}]"
        
        # JS to seek the audio player
        # On Gradio 4, the audio tag is nested. We look for it under the elem_id container.
        onclick_js = (
            f"const container = document.getElementById('{audio_elem_id}'); "
            f"if (container) {{ "
            f"  const a = container.querySelector('audio'); "
            f"  if (a) {{ a.currentTime = {start}; a.play(); }} "
            f"  else {{ console.error('Audio tag not found in {audio_elem_id}'); }} "
            f"}} else {{ console.error('Container {audio_elem_id} not found'); }}"
        )
        
        html += f"""
        <span style='cursor: pointer; padding: 2px 4px; border-radius: 4px; margin: 2px; display: inline-block; transition: background 0.2s;' 
              onmouseover="this.style.backgroundColor='#e0f7fa'" 
              onmouseout="this.style.backgroundColor='transparent'" 
              onclick="{onclick_js}">
            <strong style='color: #007bff;'>{ts_str}</strong> {text}
        </span>
        """
    html += "</div>"
    # Auto-scroll script
    html += f"<script>var el = document.getElementById('{audio_elem_id}_container'); if(el) el.scrollTop = el.scrollHeight;</script>"
    return html


# ── Live transcription callbacks ──────────────────────────────────────────────

def _live_worker_fn():
    """Background thread: consume chunks from capture and transcribe."""
    global _live_capture, _live_transcriber, _last_poll_time

    logger.info("Live worker started")
    
    # Store local references so we can drain the queue even if globals are cleared
    capture = _live_capture
    transcriber = _live_transcriber
    
    while capture and transcriber:
        # Check if capture has stopped AND queue is empty
        if not capture.is_running and len(capture._chunk_queue) == 0:
            break
            
        chunk = capture.get_chunk(timeout=0.5)
        if chunk is None:
            continue

        if chunk.is_silent:
            logger.debug("Silent chunk at offset=%.1fs, skipping", chunk.offset_s)
            continue

        try:
            transcriber.process_chunk(chunk.data, chunk.offset_s)
        except Exception:
            logger.exception("Live transcription error on chunk at %.1fs", chunk.offset_s)

    logger.info("Live worker exited")


def start_live(mic_label: str, loopback_label: str, title: str, force_language: Optional[str] = None):
    """Start live transcription session."""
    global _live_capture, _live_transcriber, _live_thread

    with _live_lock:
        if _live_transcriber and _live_transcriber.is_running:
            return "⚠️ Phiên live đang chạy!", ""

        # Resolve devices
        mic_device = None
        if mic_label:
            dev = device_by_label(mic_label)
            if dev:
                mic_device = dev.index

        loopback_device = None
        if loopback_label:
            dev = device_by_label(loopback_label)
            if dev:
                loopback_device = dev.index

        if mic_device is None and loopback_device is None:
            return "❌ Chọn ít nhất 1 thiết bị âm thanh (mic hoặc loopback).", ""

        try:
            from src.audio.live_capture import LiveCapture
            from src.live_transcribe import LiveTranscriber

            _live_capture = LiveCapture(
                mic_device=mic_device,
                loopback_device=loopback_device,
            )
            _live_transcriber = LiveTranscriber(
                title=title or "live_meeting",
                force_language=force_language,
            )

            _live_capture.start()
            _live_transcriber.start()

            global _last_poll_time
            _last_poll_time = time.time()

            _live_thread = threading.Thread(target=_live_worker_fn, daemon=True)
            _live_thread.start()

        except Exception as e:
            logger.exception("Failed to start live session")
            return f"❌ Lỗi: {e}", ""

    return "🔴 **LIVE** — Đang ghi và nhận dạng real-time …", ""


def stop_live():
    """Stop live transcription and save session."""
    global _live_capture, _live_transcriber, _live_thread

    with _live_lock:
        if _live_transcriber is None or not _live_transcriber.is_running:
            return "⚠️ Không có phiên live nào.", "", None

        audio_data = None
        # 1. Stop capture -> This forces the final chunk into the queue and stops the capture worker.
        if _live_capture:
            _live_capture.stop()
            audio_data = _live_capture.get_full_audio()
            _live_capture = None

        # 2. Wait for the live worker thread to process all remaining chunks in the queue
        if _live_thread:
            if _live_thread is not threading.current_thread():
                # Tăng timeout lên 120s vì trên CPU yếu, transcribe 20s cuối có thể mất tới 1-2 phút
                _live_thread.join(timeout=120)  
            _live_thread = None

        # 3. Stop transcriber and save (now that all chunks are processed)
        out_dir = _live_transcriber.stop()
        
        # 4. Save the continuous audio recording
        if audio_data is not None and len(audio_data) > 0 and out_dir:
            try:
                import soundfile as sf
                from src.config import SAMPLE_RATE
                wav_path = out_dir / "recording.wav"
                sf.write(str(wav_path), audio_data, SAMPLE_RATE)
            except Exception as e:
                logger.error(f"Failed to save live recording: {e}")
                
        full_text = _live_transcriber.session.get_full_text()
        langs = _live_transcriber.session.get_languages()
        duration = _live_transcriber.session.get_duration_s()
        n_updates = len(_live_transcriber.session.updates)
        updates_list = list(_live_transcriber.session.updates)

        _live_transcriber = None

    dm, ds = divmod(int(duration), 60)
    status = (
        f"✅ Phiên live kết thúc! "
        f"Thời lượng: **{dm:02d}:{ds:02d}** | "
        f"Ngôn ngữ: **{', '.join(sorted(langs)) if langs else 'N/A'}** | "
        f"Cập nhật: **{n_updates}** | "
        f"Lưu tại: `{out_dir}`"
    )

    transcript_file = str(out_dir / "transcript_live.txt") if out_dir else None
    wav_path = str(out_dir / "recording.wav") if out_dir and (out_dir / "recording.wav").exists() else None
    
    html_transcript = _render_interactive_transcript(updates_list, "live_playback_audio")
    return status, html_transcript, transcript_file, gr.update(visible=bool(wav_path), value=wav_path)


def stop_browser_live_python():
    global _browser_live_transcriber, _browser_audio_chunks
    with _browser_live_lock:
        if _browser_live_transcriber is None:
            return "⚠️ Không có phiên live nào đang chạy.", "", None, gr.update(visible=False)
            
        out_dir = _browser_live_transcriber.stop()
        
        # Save recording
        wav_path = None
        if _browser_audio_chunks and out_dir:
            try:
                full_audio = np.concatenate(_browser_audio_chunks)
                wav_file = out_dir / "recording.wav"
                sf.write(str(wav_file), full_audio, SAMPLE_RATE)
                if wav_file.exists():
                    wav_path = str(wav_file)
                logger.info("Saved browser recording to %s", wav_file)
            except Exception as e:
                logger.error("Failed to save browser recording: %s", e)
                
        # Read final updates
        updates_list = list(_browser_live_transcriber.session.updates)
        duration = _browser_live_transcriber.session.get_duration_s()
        langs = _browser_live_transcriber.session.get_languages()
        n_updates = len(updates_list)
        
        _browser_live_transcriber = None
        _browser_audio_chunks = []
        
    dm, ds = divmod(int(duration), 60)
    status = (
        f"✅ Phiên live kết thúc! "
        f"Thời lượng: **{dm:02d}:{ds:02d}** | "
        f"Ngôn ngữ: **{', '.join(sorted(langs)) if langs else 'N/A'}** | "
        f"Cập nhật: **{n_updates}** | "
        f"Lưu tại: `{out_dir}`"
    )

    transcript_file = str(out_dir / "transcript_live.txt") if out_dir else None
    html_transcript = _render_interactive_transcript(updates_list, "browser_live_playback_audio")
    
    return status, html_transcript, transcript_file, gr.update(visible=bool(wav_path), value=wav_path)


def poll_live_transcript():
    """Poll current live transcript for UI updates."""
    global _last_poll_time, _live_transcriber, _browser_live_transcriber
    _last_poll_time = time.time()

    if _live_transcriber and _live_transcriber.is_running:
        elapsed = _live_transcriber.session.get_duration_s()
        langs = _live_transcriber.session.get_languages()
        n = len(_live_transcriber.session.updates)
        em, es = divmod(int(elapsed), 60)
        status = (
            f"🔴 **LIVE** — {em:02d}:{es:02d} | "
            f"{n} đoạn | "
            f"Ngôn ngữ: {', '.join(sorted(langs)) if langs else '…'}"
        )
        html = _render_interactive_transcript(_live_transcriber.session.updates, "live_playback_audio")
        return status, html
    elif _browser_live_transcriber and _browser_live_transcriber.is_running:
        elapsed = _browser_live_transcriber.session.get_duration_s()
        langs = _browser_live_transcriber.session.get_languages()
        n = len(_browser_live_transcriber.session.updates)
        em, es = divmod(int(elapsed), 60)
        status = (
            f"🔴 **LIVE (Trình duyệt)** — {em:02d}:{es:02d} | "
            f"{n} đoạn | "
            f"Ngôn ngữ: {', '.join(sorted(langs)) if langs else '…'}"
        )
        html = _render_interactive_transcript(_browser_live_transcriber.session.updates, "browser_live_playback_audio")
        return status, html
    return gr.update(), gr.update()


# ── Audio device test ─────────────────────────────────────────────────────────

def test_audio_device(device_label: str, test_seconds: float = 3.0, play_test_sound: bool = False) -> tuple[str, str | None]:
    """
    Record a short sample from the given device and return level analysis
    + path to saved WAV for playback.
    If play_test_sound is True, plays a short tone while recording (useful for testing loopback).
    """
    if not device_label or "(Không dùng" in device_label:
        return "❌ Chưa chọn thiết bị để test.", None

    dev_match = device_by_label(device_label)
    if dev_match is None:
        return f"❌ Không tìm thấy thiết bị: {device_label}", None
    device_idx = dev_match.index

    try:
        import pyaudiowpatch as pyaudio
        p = pyaudio.PyAudio()
        dev = p.get_device_info_by_index(device_idx)
        native_rate = int(dev["defaultSampleRate"])
        channels = dev["maxInputChannels"]

        frames = []

        def cb(in_data, frame_count, time_info, status):
            data_np = np.frombuffer(in_data, dtype=np.float32)
            if channels > 1:
                data_np = data_np.reshape(-1, channels).mean(axis=1)
                
            if native_rate != SAMPLE_RATE:
                import scipy.signal
                target_len = int(len(data_np) * SAMPLE_RATE / native_rate)
                data_np = scipy.signal.resample(data_np, target_len)
                
            frames.append(data_np.astype(np.float32))
            return (None, pyaudio.paContinue)

        # Start a background thread to play a test sound if requested
        if play_test_sound:
            def _play_sound():
                t = np.linspace(0, test_seconds, int(SAMPLE_RATE * test_seconds), False)
                tone = (np.sin(440 * 2 * np.pi * t) * 0.1).astype(np.float32)
                try:
                    import sounddevice as sd
                    sd.play(tone, samplerate=SAMPLE_RATE)
                    sd.wait()
                except Exception as e:
                    logger.error(f"Could not play test tone: {e}")
            
            threading.Thread(target=_play_sound, daemon=True).start()
            time.sleep(0.1) # Give it a tiny moment to start playing before we record

        stream = p.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=native_rate,
            input=True,
            input_device_index=dev["index"],
            stream_callback=cb,
            frames_per_buffer=int(native_rate * 0.1)
        )

        stream.start_stream()
        time.sleep(test_seconds)
        stream.stop_stream()
        stream.close()
        p.terminate()

        if not frames:
            return "❌ Không nhận được dữ liệu từ thiết bị!", None

        audio = np.concatenate(frames, axis=0)
        rms = float(np.sqrt(np.mean(audio ** 2)))
        peak = float(np.abs(audio).max())

        # Visual level bar
        bar_length = 20
        level_pct = min(rms / 0.1, 1.0)  # normalize: 0.1 RMS = 100%
        filled = int(level_pct * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)

        # Level assessment
        if rms < 0.001:
            verdict = "🔇 **IM LẶNG** — Thiết bị không nhận tín hiệu"
            tip = "→ Kiểm tra thiết bị đã bật chưa, hoặc chọn thiết bị khác."
        elif rms < 0.005:
            verdict = "🔈 **RẤT NHỎ** — Có tín hiệu nhưng rất yếu"
            tip = "→ Tăng volume trong Sound Settings hoặc nói to hơn."
        elif rms < 0.02:
            verdict = "🔉 **BÌNH THƯỜNG** — Tín hiệu ổn"
            tip = "✅ Thiết bị hoạt động tốt!"
        else:
            verdict = "🔊 **TỐT** — Tín hiệu mạnh, rõ ràng"
            tip = "✅ Thiết bị hoạt động rất tốt!"

        # Save WAV for playback
        test_dir = Path("outputs/audio_tests")
        test_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in dev["name"])[:30]
        wav_path = test_dir / f"test_{dev['index']}_{safe_name}.wav"
        sf.write(str(wav_path), audio, SAMPLE_RATE)

        result = (
            f"**[{dev['index']}] {dev['name']}**\n\n"
            f"Mức âm: `{bar}` {level_pct*100:.0f}%\n\n"
            f"RMS: `{rms:.6f}` | Peak: `{peak:.6f}`\n\n"
            f"{verdict}\n\n"
            f"{tip}"
        )
        return result, str(wav_path)

    except Exception as e:
        return f"❌ Lỗi khi test thiết bị: {e}", None


# ── Build UI ──────────────────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    # Check Ollama on startup
    ollama_ok = is_ollama_available()
    ollama_warning = (
        "" if ollama_ok
        else "\n> ⚠️ **Ollama không kết nối được** — chạy `ollama serve` và `ollama pull qwen2.5:7b-instruct`"
    )

    with gr.Blocks(
        title="🎙️ Meeting Transcriber — JA / EN / VI",
    ) as demo:

        gr.Markdown(
            f"""
# 🎙️ Ghi Chép Cuộc Họp — Đa Ngôn Ngữ (Nhật / Anh / Việt)
Tự động nhận dạng giọng nói · **Per-chunk multilingual** · Phân tách người nói · Dịch sang tiếng Việt · Tóm tắt{ollama_warning}
"""
        )

        # ── Tab 1: Input (batch mode) ────────────────────────────────────────
        with gr.Tab("📥 Đầu vào"):
            input_mode = gr.Radio(
                choices=["📁 Tải file lên", "🎤 Ghi âm (mic / loopback)"],
                value="📁 Tải file lên",
                label="Chế độ đầu vào",
            )

            with gr.Group(visible=True) as file_group:
                uploaded_file = gr.File(
                    label="Tải file âm thanh / video (mp3, wav, mp4, m4a, …)",
                    file_types=["audio", "video"],
                )

            with gr.Group(visible=False) as record_group:
                gr.Markdown(_loopback_hint_md())
                device_dropdown = gr.Dropdown(
                    choices=device_names(),
                    label="Chọn thiết bị âm thanh đầu vào",
                    allow_custom_value=True,
                    value=str(find_loopback_device()) if find_loopback_device() else None,
                )
                with gr.Row():
                    btn_start = gr.Button("🔴 Bắt đầu ghi", variant="primary")
                    btn_stop  = gr.Button("⏹️ Dừng ghi", variant="stop")
                rec_status  = gr.Textbox(label="Trạng thái ghi", interactive=False)
                rec_wav_path = gr.Textbox(label="File WAV đã ghi", interactive=False, visible=False)

            def toggle_mode(mode):
                is_file = mode == "📁 Tải file lên"
                return gr.update(visible=is_file), gr.update(visible=not is_file)

            input_mode.change(toggle_mode, inputs=input_mode, outputs=[file_group, record_group])
            btn_start.click(start_recording, inputs=[device_dropdown], outputs=[rec_status, rec_wav_path])
            btn_stop.click(stop_recording, outputs=[rec_status, rec_wav_path])

            gr.Markdown("---")
            with gr.Row():
                title_box = gr.Textbox(
                    label="Tên cuộc họp (dùng đặt tên thư mục output)",
                    placeholder="Ví dụ: Sprint Review Q2",
                    value="",
                )
                num_speakers_box = gr.Textbox(
                    label="Số người nói (để trống nếu không biết)",
                    placeholder="2",
                    value="",
                )
            skip_diar_chk = gr.Checkbox(
                label="⏭️ Bỏ qua phân tách người nói (nhanh hơn, không cần HF_TOKEN)",
                value=False,
            )

            btn_process = gr.Button("🚀 Xử lý", variant="primary", size="lg")
            status_box  = gr.Markdown("")

        # ── Tab 2: Transcript (batch) ─────────────────────────────────────────
        with gr.Tab("📄 Transcript"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### 🌏 Bản gốc (ngôn ngữ gốc)")
                    orig_box = gr.Textbox(
                        label="Transcript gốc (có nhãn người nói + thời gian)",
                        lines=25,
                        interactive=False,
                    )
                    dl_orig = gr.File(label="⬇️ Tải transcript gốc (.txt)", visible=False)

                with gr.Column():
                    gr.Markdown("### 🇻🇳 Dịch tiếng Việt")
                    vi_box = gr.Textbox(
                        label="Transcript dịch sang tiếng Việt",
                        lines=25,
                        interactive=False,
                    )
                    dl_vi = gr.File(label="⬇️ Tải bản dịch (.txt)", visible=False)

        # ── Tab 3: Summary (batch) ────────────────────────────────────────────
        with gr.Tab("📋 Tóm tắt"):
            sum_md = gr.Markdown("*(Chưa có tóm tắt — nhấn Xử lý ở tab Đầu vào)*")
            dl_sum = gr.File(label="⬇️ Tải tóm tắt (.md)", visible=False)

        # ── Tab 4: LIVE Transcription ─────────────────────────────────────────
        with gr.Tab("🔴 Live"):
            gr.Markdown(
                """
### 🔴 Transcript Live — Real-time

Ghi âm và nhận dạng **trực tiếp** trong cuộc họp.
Chọn **mic** (giọng bạn) và/hoặc **loopback** (âm thanh hệ thống từ loa) để bắt cả hai chiều.
"""
            )

            gr.Markdown(_loopback_hint_md())

            with gr.Row():
                with gr.Column(scale=4):
                    live_mic = gr.Dropdown(
                        choices=["(Không dùng mic)"] + device_names(),
                        label="🎤 Microphone",
                        value="(Không dùng mic)",
                        allow_custom_value=True,
                    )
                with gr.Column(scale=1, min_width=100):
                    btn_test_mic = gr.Button("🔊 Test Mic", size="sm")

            with gr.Row():
                with gr.Column(scale=4):
                    live_loopback = gr.Dropdown(
                        choices=["(Không dùng loopback)"] + device_names(),
                        label="🔊 System Audio (Loopback)",
                        value=(
                            str(find_loopback_device())
                            if find_loopback_device()
                            else "(Không dùng loopback)"
                        ),
                        allow_custom_value=True,
                    )
                with gr.Column(scale=1, min_width=100):
                    btn_test_loopback = gr.Button("🔊 Test Loa", size="sm")

            # Test result area
            with gr.Accordion("📊 Kết quả test thiết bị", open=False) as test_accordion:
                test_result_md = gr.Markdown("*Nhấn 'Test Mic' hoặc 'Test Loa' để kiểm tra (ghi 3 giây)*")
                test_audio_player = gr.Audio(
                    label="🔈 Nghe lại mẫu thu",
                    type="filepath",
                    visible=False,
                )

            # Wire test buttons
            def _test_mic(label):
                result, wav = test_audio_device(label)
                return (
                    result,
                    gr.update(visible=wav is not None, value=wav),
                    gr.Accordion(open=True),
                )

            def _test_loopback(label):
                result, wav = test_audio_device(label, play_test_sound=True)
                return (
                    result,
                    gr.update(visible=wav is not None, value=wav),
                    gr.Accordion(open=True),
                )

            btn_test_mic.click(
                fn=_test_mic,
                inputs=[live_mic],
                outputs=[test_result_md, test_audio_player, test_accordion],
            )
            btn_test_loopback.click(
                fn=_test_loopback,
                inputs=[live_loopback],
                outputs=[test_result_md, test_audio_player, test_accordion],
            )

            with gr.Row():
                live_title = gr.Textbox(
                    label="Tên cuộc họp",
                    placeholder="Daily Standup",
                    value="",
                    scale=2,
                )
                live_language = gr.Radio(
                    choices=["Auto", "vi", "en", "ja"],
                    value="Auto",
                    label="🌐 Ngôn ngữ (chọn nhanh)",
                    scale=1,
                )

            live_auto_process_chk = gr.Checkbox(
                label="☑️ Tự động Xử lý chuyên sâu (Phân biệt người nói & Tóm tắt) sau khi kết thúc Live",
                value=True,
            )

            with gr.Row():
                btn_live_start = gr.Button(
                    "🔴 Bắt đầu Live",
                    variant="primary",
                    size="lg",
                )
                btn_live_stop = gr.Button(
                    "⏹️ Dừng & Lưu",
                    variant="stop",
                    size="lg",
                )

            live_status = gr.Markdown("*Chưa bắt đầu*")

            live_playback = gr.Audio(
                label="🔈 Phát lại Audio gốc (có thể click vào transcript bên dưới để nghe)",
                type="filepath",
                visible=False,
                elem_id="live_playback_audio"
            )

            live_transcript = gr.HTML(
                label="Transcript trực tiếp",
                value="<div style='padding: 10px; color: #666;'>Chưa có dữ liệu...</div>"
            )

            dl_live = gr.File(label="⬇️ Tải transcript live (.txt)", visible=False)
            
            # ── Post-processing UI (Hidden initially) ──
            with gr.Group(visible=False) as live_post_group:
                gr.Markdown("---")
                gr.Markdown("### ⚙️ Kết quả Xử lý Chuyên sâu")
                live_post_status = gr.Markdown("⏳ Đang đợi xử lý...")
                with gr.Row():
                    live_post_vi = gr.Textbox(label="Bản dịch tinh chỉnh (Đã phân biệt người nói)", lines=15, interactive=False)
                    live_post_sum = gr.Markdown("*(Đang tóm tắt...)*")

            # ── Live button wiring ────────────────────────────────────────────
            def _resolve_live_device(label: str) -> str:
                """Return empty string if 'not using' option is selected."""
                if "(Không dùng" in label:
                    return ""
                return label

            def _resolve_lang(choice: str) -> Optional[str]:
                if "vi" in choice: return "vi"
                if "en" in choice: return "en"
                if "ja" in choice: return "ja"
                return None

            def _start_live_wrapper(mic_label, lb_label, title, lang_choice):
                mic = _resolve_live_device(mic_label)
                lb = _resolve_live_device(lb_label)
                lang = _resolve_lang(lang_choice)
                status, _ = start_live(mic, lb, title, lang)
                return status, ""

            def _update_live_lang(lang_choice):
                global _live_transcriber
                if _live_transcriber:
                    _live_transcriber.force_language = _resolve_lang(lang_choice)

            live_language.change(fn=_update_live_lang, inputs=[live_language])

            btn_live_start.click(
                fn=_start_live_wrapper,
                inputs=[live_mic, live_loopback, live_title, live_language],
                outputs=[live_status, live_transcript],
            )

            def _stop_live_wrapper():
                status, html, fpath, audio_upd = stop_live()
                # fpath là đường dẫn tới transcript txt. file wav được tạo trong cùng thư mục
                wav_path = None
                if fpath:
                    import os
                    dir_path = os.path.dirname(fpath)
                    wav_file = os.path.join(dir_path, "recording.wav")
                    if os.path.exists(wav_file):
                        wav_path = wav_file
                return (
                    status,
                    html,
                    gr.update(visible=bool(fpath), value=fpath),
                    audio_upd,
                    wav_path
                )

            # Hidden textbox to store wav path from stop_live
            live_wav_path_hidden = gr.Textbox(visible=False)

            btn_live_stop.click(
                fn=_stop_live_wrapper,
                outputs=[live_status, live_transcript, dl_live, live_playback, live_wav_path_hidden],
            )
            
            # Chain the post-process
            def check_auto_process(wav, do_auto):
                if not wav or not do_auto:
                    return gr.update(visible=False), "Không tự động xử lý chuyên sâu."
                return gr.update(visible=True), "🚀 Đang bắt đầu xử lý chuyên sâu..."

            live_wav_path_hidden.change(
                fn=check_auto_process,
                inputs=[live_wav_path_hidden, live_auto_process_chk],
                outputs=[live_post_group, live_post_status]
            ).then(
                fn=lambda do_auto: None if not do_auto else None,
                inputs=[live_auto_process_chk],
                outputs=[]
            ) # Wait for UI to update

            # Bind process directly
            def _live_run_process(wav, do_auto, title, progress=gr.Progress(track_tqdm=False)):
                if not wav or not do_auto:
                    return "Bỏ qua.", "", ""
                
                # Gọi thẳng hàm process dùng chung bên tab Batch
                # (input_mode, uploaded_file, device_label, title, num_speakers_str, skip_diarization, progress)
                status, orig, vi, summ, dl_orig, dl_vi, dl_sum = process(
                    "📁 Tải file lên",
                    wav,
                    None,
                    title,
                    "",
                    False,
                    progress
                )
                return status, vi, summ

            live_wav_path_hidden.change(
                fn=_live_run_process,
                inputs=[live_wav_path_hidden, live_auto_process_chk, live_title],
                outputs=[live_post_status, live_post_vi, live_post_sum],
                trigger_mode="once"
            )

            # Auto-refresh live transcript with Timer
            live_timer = gr.Timer(value=3, active=False)

            def _poll():
                return poll_live_transcript()

            live_timer.tick(fn=_poll, outputs=[live_status, live_transcript])

            # Activate timer when live starts, deactivate when stops
            btn_live_start.click(
                fn=lambda: gr.Timer(active=True),
                outputs=[live_timer],
            )
            btn_live_stop.click(
                fn=lambda: gr.Timer(active=False),
                outputs=[live_timer],
            )

        with gr.Tab("🌐 Live từ Trình duyệt"):
            gr.Markdown(
                """
### 🌐 Live từ Trình duyệt (Không cần VB-CABLE)

Ghi âm và bóc băng trực tiếp thông qua micro và âm thanh của trình duyệt mà không cần cài đặt bất kỳ phần mềm loopback nào!
- **Microphone:** phù hợp họp trực tiếp, chỉ thu giọng nói từ micro.
- **System / Tab:** phù hợp Google Meet, Zoom web hoặc video; khi được hỏi, hãy bật **"Chia sẻ âm thanh"**.
- **Cả hai:** thu đồng thời micro và âm thanh tab/hệ thống, phù hợp họp trực tuyến.
"""
            )

            browser_js_code = """
            <script>
            // Biến toàn cục kiểm soát ghi âm ở trình duyệt
            window.browserAudioActive = false;
            window.browserAudioCtx = null;
            window.browserAudioProcessor = null;
            window.browserAudioStreams = [];
            window.browserAudioOffset = 0;

            async function startBrowserAudioCapture(title, lang, echoCancellation, noiseSuppression, autoGainControl) {
                if (window.browserAudioActive) return;
                
                try {
                    // Lọc nguồn âm thanh từ radio buttons của Gradio
                    const sourceChoice = document.querySelector("#browser_audio_source input:checked")?.value || "🎙️ Cả hai";
                    console.log("Selected source:", sourceChoice);
                    
                    let micStream = null;
                    let systemStream = null;
                    
                    if (sourceChoice.includes("Microphone") || sourceChoice.includes("Cả hai")) {
                        micStream = await navigator.mediaDevices.getUserMedia({
                            audio: {
                                echoCancellation: Boolean(echoCancellation),
                                noiseSuppression: Boolean(noiseSuppression),
                                autoGainControl: Boolean(autoGainControl)
                            }
                        });
                    }
                    
                    if (sourceChoice.includes("System / Tab") || sourceChoice.includes("Cả hai")) {
                        systemStream = await navigator.mediaDevices.getDisplayMedia({
                            video: { width: 1, height: 1 },
                            audio: true
                        });
                        if (!systemStream.getAudioTracks().length) {
                            systemStream.getTracks().forEach(track => track.stop());
                            throw new Error("Không nhận được audio từ tab/hệ thống. Hãy bật 'Chia sẻ âm thanh'.");
                        }
                    }
                    
                    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
                    const audioCtx = new AudioContextClass({ sampleRate: 16000 });
                    window.browserAudioCtx = audioCtx;
                    
                    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
                    window.browserAudioProcessor = processor;
                    
                    let merger = null;
                    let micSource = null;
                    let systemSource = null;
                    
                    if (micStream && systemStream) {
                        merger = audioCtx.createChannelMerger(2);
                        micSource = audioCtx.createMediaStreamSource(micStream);
                        systemSource = audioCtx.createMediaStreamSource(systemStream);
                        micSource.connect(merger, 0, 0);
                        systemSource.connect(merger, 0, 1);
                        
                        // Mix down to mono
                        const mixNode = audioCtx.createGain();
                        merger.connect(mixNode);
                        mixNode.connect(processor);
                    } else if (micStream) {
                        micSource = audioCtx.createMediaStreamSource(micStream);
                        micSource.connect(processor);
                    } else if (systemStream) {
                        systemSource = audioCtx.createMediaStreamSource(systemStream);
                        systemSource.connect(processor);
                    } else {
                        alert("Vui lòng chọn ít nhất 1 nguồn âm thanh!");
                        return;
                    }
                    
                    // Keep ScriptProcessor alive without playing the captured meeting back.
                    const silentSink = audioCtx.createGain();
                    silentSink.gain.value = 0;
                    processor.connect(silentSink);
                    silentSink.connect(audioCtx.destination);
                    
                    window.browserAudioStreams = [micStream, systemStream].filter(s => s !== null);
                    window.browserAudioActive = true;
                    window.browserAudioOffset = 0;
                    
                    let buffer = [];
                    const chunkSamples = 5 * 16000; // 5s chunk
                    
                    processor.onaudioprocess = (e) => {
                        if (!window.browserAudioActive) return;
                        const channelData = e.inputBuffer.getChannelData(0);
                        buffer.push(...channelData);
                        
                        if (buffer.length >= chunkSamples) {
                            const chunk = buffer.slice(0, chunkSamples);
                            buffer = buffer.slice(chunkSamples);
                            
                            const currentOffset = window.browserAudioOffset;
                            window.browserAudioOffset += 5;
                            
                            sendAudioChunk(chunk, currentOffset);
                        }
                    };
                    
                    // Gọi API start của FastAPI backend
                    const formData = new FormData();
                    formData.append("title", title || "live_meeting");
                    formData.append("force_language", lang || "Auto");
                    
                    fetch("/api/live/start", {
                        method: "POST",
                        body: formData
                    }).then(res => res.json())
                      .then(data => console.log("Session started on server:", data))
                      .catch(err => console.error("Error starting server session:", err));

                    console.log("Browser capture started successfully.");
                } catch (err) {
                    console.error("Error starting browser capture:", err);
                    alert("Lỗi khởi tạo thu âm trình duyệt: " + err.message);
                    window.browserAudioActive = false;
                }
            }

            function sendAudioChunk(samples, offset) {
                const float32Array = new Float32Array(samples);
                const buffer = float32Array.buffer;
                
                fetch(`/api/live/chunk?offset_s=${offset}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/octet-stream'
                    },
                    body: buffer
                }).then(res => res.json())
                  .then(data => console.log(`Sent chunk at ${offset}s`, data))
                  .catch(err => console.error("Error sending chunk:", err));
            }

            function stopBrowserAudioCapture() {
                window.browserAudioActive = false;
                
                if (window.browserAudioProcessor) {
                    window.browserAudioProcessor.disconnect();
                    window.browserAudioProcessor = null;
                }
                
                if (window.browserAudioCtx) {
                    window.browserAudioCtx.close();
                    window.browserAudioCtx = null;
                }
                
                if (window.browserAudioStreams) {
                    window.browserAudioStreams.forEach(stream => {
                        stream.getTracks().forEach(track => track.stop());
                    });
                    window.browserAudioStreams = [];
                }
                console.log("Browser capture stopped.");
            }
            </script>
            """
            gr.HTML(browser_js_code)

            with gr.Row():
                browser_audio_src = gr.Radio(
                    choices=[
                        "🎙️ Microphone",
                        "🖥️ System / Tab",
                        "🎙️ Cả hai",
                    ],
                    value="🎙️ Cả hai",
                    label="Nguồn âm thanh",
                    elem_id="browser_audio_source"
                )

            browser_source_hint = gr.Markdown(
                "**Cả hai:** thu micro và âm thanh tab/hệ thống cho các cuộc họp trực tuyến.",
                elem_id="browser_source_hint",
            )

            def _browser_source_hint(source: str) -> str:
                if source == "🎙️ Microphone":
                    return "**Microphone:** phù hợp họp trực tiếp; chỉ thu âm thanh từ micro."
                if source == "🖥️ System / Tab":
                    return "**System / Tab:** chọn tab hoặc màn hình và bật **Chia sẻ âm thanh**."
                return "**Cả hai:** thu micro và âm thanh tab/hệ thống cho các cuộc họp trực tuyến."

            browser_audio_src.change(
                fn=_browser_source_hint,
                inputs=[browser_audio_src],
                outputs=[browser_source_hint],
            )

            with gr.Accordion("⚙️ Cài đặt microphone", open=False):
                gr.Markdown(
                    "Các tuỳ chọn này áp dụng cho nguồn **Microphone** và **Cả hai**."
                )
                with gr.Row():
                    browser_echo_chk = gr.Checkbox(
                        label="Echo cancellation",
                        info="Giảm tiếng loa lọt vào micro",
                        value=True,
                    )
                    browser_noise_chk = gr.Checkbox(
                        label="Noise suppression",
                        info="Lọc nhiễu nền",
                        value=True,
                    )
                    browser_agc_chk = gr.Checkbox(
                        label="Auto gain control",
                        info="Tự cân bằng âm lượng micro",
                        value=False,
                    )

            with gr.Row():
                browser_title = gr.Textbox(
                    label="Tên cuộc họp",
                    placeholder="Cuộc họp qua Browser",
                    value="",
                    scale=2,
                )
                browser_language = gr.Radio(
                    choices=["Auto", "vi", "en", "ja"],
                    value="Auto",
                    label="🌐 Ngôn ngữ (chọn nhanh)",
                    scale=1,
                )

            browser_auto_process_chk = gr.Checkbox(
                label="☑️ Tự động Xử lý chuyên sâu (Phân biệt người nói & Tóm tắt) sau khi kết thúc Live",
                value=True,
            )

            with gr.Row():
                btn_browser_start = gr.Button(
                    "🔴 Khởi động & Ghi âm",
                    variant="primary",
                    size="lg",
                )
                btn_browser_stop = gr.Button(
                    "⏹️ Dừng & Lưu",
                    variant="stop",
                    size="lg",
                )

            browser_status = gr.Markdown("*Chưa bắt đầu*")

            browser_playback = gr.Audio(
                label="🔈 Phát lại Audio gốc (có thể click vào transcript bên dưới để nghe)",
                type="filepath",
                visible=False,
                elem_id="browser_live_playback_audio"
            )

            browser_transcript = gr.HTML(
                label="Transcript trực tiếp",
                value="<div style='padding: 10px; color: #666;'>Chưa có dữ liệu...</div>"
            )

            dl_browser_live = gr.File(label="⬇️ Tải transcript live (.txt)", visible=False)

            # ── Post-processing UI (Hidden initially) ──
            with gr.Group(visible=False) as browser_post_group:
                gr.Markdown("---")
                gr.Markdown("### ⚙️ Kết quả Xử lý Chuyên sâu")
                browser_post_status = gr.Markdown("⏳ Đang đợi xử lý...")
                with gr.Row():
                    browser_post_vi = gr.Textbox(label="Bản dịch tinh chỉnh (Đã phân biệt người nói)", lines=15, interactive=False)
                    browser_post_sum = gr.Markdown("*(Đang tóm tắt...)*")

            # ── Browser live button wiring ────────────────────────────────────
            def _start_browser_live_wrapper(
                title,
                lang_choice,
                echo_cancellation,
                noise_suppression,
                auto_gain_control,
            ):
                lang = _resolve_lang(lang_choice)
                global _browser_live_transcriber, _browser_audio_chunks, _browser_live_title
                with _browser_live_lock:
                    if _browser_live_transcriber and _browser_live_transcriber.is_running:
                        return "⚠️ Phiên live đang chạy!", ""
                    
                    from src.live_transcribe import LiveTranscriber
                    _browser_live_title = title or "live_meeting"
                    _browser_live_transcriber = LiveTranscriber(
                        title=_browser_live_title,
                        force_language=lang
                    )
                    _browser_live_transcriber.start()
                    _browser_audio_chunks = []
                return "🔴 **LIVE (Trình duyệt)** — Đang ghi và nhận dạng từ trình duyệt …", ""

            def _update_browser_live_lang(lang_choice):
                global _browser_live_transcriber
                if _browser_live_transcriber:
                    _browser_live_transcriber.force_language = _resolve_lang(lang_choice)

            browser_language.change(fn=_update_browser_live_lang, inputs=[browser_language])

            # Trigger JS start capturing on browser
            btn_browser_start.click(
                fn=_start_browser_live_wrapper,
                inputs=[
                    browser_title,
                    browser_language,
                    browser_echo_chk,
                    browser_noise_chk,
                    browser_agc_chk,
                ],
                outputs=[browser_status, browser_transcript],
                js="async (title, lang, echo, noise, agc) => { await startBrowserAudioCapture(title, lang, echo, noise, agc); }"
            )

            # Auto-refresh live transcript with Timer
            browser_timer = gr.Timer(value=3, active=False)

            def _poll_browser():
                return poll_live_transcript()

            browser_timer.tick(fn=_poll_browser, outputs=[browser_status, browser_transcript])

            # Activate timer
            btn_browser_start.click(
                fn=lambda: gr.Timer(active=True),
                outputs=[browser_timer],
            )

            # Stop browser live and show results
            def _stop_browser_live_wrapper():
                status, html, fpath, audio_upd = stop_browser_live_python()
                wav_path = None
                if fpath:
                    import os
                    dir_path = os.path.dirname(fpath)
                    wav_file = os.path.join(dir_path, "recording.wav")
                    if os.path.exists(wav_file):
                        wav_path = wav_file
                return (
                    status,
                    html,
                    gr.update(visible=bool(fpath), value=fpath),
                    audio_upd,
                    wav_path
                )

            # Hidden textbox to store wav path from stop
            browser_wav_path_hidden = gr.Textbox(visible=False)

            btn_browser_stop.click(
                fn=_stop_browser_live_wrapper,
                outputs=[browser_status, browser_transcript, dl_browser_live, browser_playback, browser_wav_path_hidden],
                js="() => { stopBrowserAudioCapture(); }"
            )
            
            btn_browser_stop.click(
                fn=lambda: gr.Timer(active=False),
                outputs=[browser_timer],
            )

            # Chain the post-process
            browser_wav_path_hidden.change(
                fn=check_auto_process,
                inputs=[browser_wav_path_hidden, browser_auto_process_chk],
                outputs=[browser_post_group, browser_post_status]
            )

            def _browser_run_process(wav, do_auto, title, progress=gr.Progress(track_tqdm=False)):
                if not wav or not do_auto:
                    return "Bỏ qua.", "", ""
                status, orig, vi, summ, dl_orig, dl_vi, dl_sum = process(
                    "📁 Tải file lên",
                    wav,
                    None,
                    title,
                    "",
                    False,
                    progress
                )
                return status, vi, summ

            browser_wav_path_hidden.change(
                fn=_browser_run_process,
                inputs=[browser_wav_path_hidden, browser_auto_process_chk, browser_title],
                outputs=[browser_post_status, browser_post_vi, browser_post_sum],
                trigger_mode="once"
            )

        # ── Wire up batch process button ──────────────────────────────────────
        def _process_wrapper(mode, f, dev, title, ns, skip, progress=gr.Progress()):
            audio = f
            return process(mode, audio, dev, title, ns, skip, progress)

        btn_process.click(
            fn=_process_wrapper,
            inputs=[
                input_mode,
                uploaded_file,
                device_dropdown,
                title_box,
                num_speakers_box,
                skip_diar_chk,
            ],
            outputs=[
                status_box,
                orig_box,
                vi_box,
                sum_md,
                dl_orig,
                dl_vi,
                dl_sum,
            ],
            show_progress="full",
        )

        # Show download buttons after processing
        def make_files_visible(o, v, s):
            return (
                gr.update(visible=bool(o), value=o),
                gr.update(visible=bool(v), value=v),
                gr.update(visible=bool(s), value=s),
            )

        btn_process.click(
            fn=lambda o, v, s: make_files_visible(o, v, s),
            inputs=[dl_orig, dl_vi, dl_sum],
            outputs=[dl_orig, dl_vi, dl_sum],
        )

        # ── Tab 5: Analytics & Monitoring (MLOps) ────────────────────────────
        with gr.Tab("📊 Thống kê & Giám sát"):
            gr.Markdown("## 📊 Báo cáo Hiệu năng & Chỉ số Giám sát (MLOps Dashboard)")
            gr.Markdown("Thống kê thời gian xử lý thực tế của các cấu phần và hiệu năng của hệ thống cục bộ.")
            
            btn_refresh_db = gr.Button("🔄 Cập nhật dữ liệu", variant="secondary")
            
            kpi_html = gr.HTML(value="")
            
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### ⏳ Phân rã độ trễ trung bình (Latency Breakdown)")
                    latency_table_md = gr.Markdown("")
                with gr.Column():
                    lang_dist_md = gr.Markdown("")

            def refresh_stats():
                from src.monitoring import get_monitoring_stats
                stats = get_monitoring_stats()
                if not stats:
                    return (
                        "<div style='padding: 20px; text-align: center; color: #888; font-size: 16px; border: 1px dashed #ccc; border-radius: 8px;'>Chưa có dữ liệu thống kê. Hãy bóc băng vài cuộc họp để cập nhật!</div>",
                        "Chưa có dữ liệu.",
                        "Chưa có dữ liệu."
                    )
                
                kpi = f"""
<div style="display: flex; gap: 20px; margin-bottom: 20px;">
    <div style="flex: 1; padding: 15px; border-radius: 8px; background: #eaf1fb; border: 1px solid #d0e2ff; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
        <span style="font-size: 13px; color: #666; font-weight: bold; text-transform: uppercase;">Tổng số cuộc họp</span>
        <h2 style="margin: 10px 0 0 0; color: #0f62fe; font-size: 32px; font-family: sans-serif;">{stats['total_meetings']}</h2>
    </div>
    <div style="flex: 1; padding: 15px; border-radius: 8px; background: #eaf6ec; border: 1px solid #a6e5b4; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
        <span style="font-size: 13px; color: #666; font-weight: bold; text-transform: uppercase;">Tổng thời lượng bóc băng</span>
        <h2 style="margin: 10px 0 0 0; color: #198038; font-size: 32px; font-family: sans-serif;">{stats['total_duration_mins']} phút</h2>
    </div>
    <div style="flex: 1; padding: 15px; border-radius: 8px; background: #fff8e6; border: 1px solid #ffd8a8; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
        <span style="font-size: 13px; color: #666; font-weight: bold; text-transform: uppercase;">Real-Time Factor (RTF)</span>
        <h2 style="margin: 10px 0 0 0; color: #d97706; font-size: 32px; font-family: sans-serif;">{stats['average_rtf']:.4f}</h2>
        <span style="font-size: 11px; color: #888; display: block; margin-top: 5px;">(RTF < 1: Nhanh hơn thời gian thực)</span>
    </div>
</div>
"""
                lat_table = "| Quy trình (Pipeline Step) | Độ trễ trung bình | Tỷ lệ đóng góp (%) |\n| :--- | :--- | :--- |\n"
                for step, latency in stats['average_step_times_s'].items():
                    share = stats['step_shares_pct'][step]
                    lat_table += f"| ⚙️ **{step.capitalize()}** | {latency:.2f} giây | {share:.1f} % |\n"
                
                lang = "### 🌐 Phân bố ngôn ngữ hội thoại\n"
                for l, count in stats['language_distribution'].items():
                    pct = (count / stats['total_meetings']) * 100
                    filled = int(pct / 10)
                    bar = "█" * filled + "░" * (10 - filled)
                    lang += f"- **{l.upper()}**: {count} cuộc họp (`{bar}` {pct:.1f}%)\n"
                    
                return kpi, lat_table, lang

            btn_refresh_db.click(
                fn=refresh_stats,
                outputs=[kpi_html, latency_table_md, lang_dist_md]
            )
            # Load stats on startup
            demo.load(
                fn=refresh_stats,
                outputs=[kpi_html, latency_table_md, lang_dist_md]
            )

    return demo


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo = build_ui()
    # Bọc Gradio app bằng FastAPI app
    app = gr.mount_gradio_app(fastapi_app, demo, path="/")
    
    # Tự động mở trình duyệt
    import webbrowser
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://localhost:7860")
        
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Khởi chạy uvicorn
    logger.info("Starting uvicorn server on http://localhost:7860")
    uvicorn.run(app, host="0.0.0.0", port=7860)
