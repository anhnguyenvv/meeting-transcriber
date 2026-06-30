from src.config import IS_MAC, IS_WIN

def get_loopback_hint_md() -> str:
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
