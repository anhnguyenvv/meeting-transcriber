import os
import json
import subprocess
from pathlib import Path
import imageio_ffmpeg

def main():
    # Make sure tests/samples exists
    samples_dir = Path(__file__).parent / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Install gTTS if not installed
    try:
        from gtts import gTTS
    except ImportError:
        print("Installing gtts package...")
        subprocess.check_call(["pip", "install", "gtts"])
        from gtts import gTTS

    print("Generating TTS text...")
    # Define ground truth texts
    ground_truths = {
        "sample_vi.wav": "chào mọi người cảm ơn đã tham gia cuộc họp hôm nay chúng ta sẽ bắt đầu ngay bây giờ",
        "sample_en.wav": "first on the agenda we need to discuss the upcoming product launch the marketing team has prepared some materials",
        "sample_ja.wav": "はい マーケティングチームからの報告です 現在の進行状況は予定通りです 問題はありません"
    }

    # Raw texts for gTTS
    texts = {
        "sample_vi.wav": ("Chào mọi người. Cảm ơn đã tham gia cuộc họp hôm nay. Chúng ta sẽ bắt đầu ngay bây giờ.", "vi"),
        "sample_en.wav": ("First on the agenda, we need to discuss the upcoming product launch. The marketing team has prepared some materials.", "en"),
        "sample_ja.wav": ("はい、マーケティングチームからの報告です。現在の進行状況 is予定通りです。問題はありません。", "ja")
    }

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    for name, (text, lang) in texts.items():
        mp3_temp = samples_dir / name.replace(".wav", ".mp3")
        wav_out = samples_dir / name
        
        print(f"Creating TTS MP3 for {name} ({lang})...")
        tts = gTTS(text, lang=lang)
        tts.save(str(mp3_temp))
        
        print(f"Converting {name.replace('.wav', '.mp3')} to 16kHz mono WAV via FFmpeg...")
        # Run FFmpeg to convert to 16kHz mono WAV
        cmd = [
            ffmpeg_exe, "-y",
            "-i", str(mp3_temp),
            "-ar", "16000",
            "-ac", "1",
            str(wav_out)
        ]
        
        # Hide command window on Windows if needed, subprocess.DEVNULL to silence output
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        # Clean up temporary mp3
        if mp3_temp.exists():
            os.remove(mp3_temp)

    # Write ground truth JSON file
    gt_file = samples_dir / "ground_truth.json"
    with open(gt_file, "w", encoding="utf-8") as f:
        json.dump(ground_truths, f, ensure_ascii=False, indent=2)
        
    print(f"Success! Test data and ground truth generated in: {samples_dir}")

if __name__ == "__main__":
    main()
