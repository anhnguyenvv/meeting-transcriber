import os
from gtts import gTTS

def main():
    print("Generating TTS audio...")
    tts_vi = gTTS("Chào mọi người. Cảm ơn đã tham gia cuộc họp hôm nay. Chúng ta sẽ bắt đầu ngay bây giờ.", lang='vi')
    tts_vi.save("sample_vi.mp3")

    tts_en = gTTS("First on the agenda, we need to discuss the upcoming product launch. The marketing team has prepared some materials.", lang='en')
    tts_en.save("sample_en.mp3")

    tts_ja = gTTS("はい、マーケティングチームからの報告です。現在の進行状況は予定通りです。問題はありません。", lang='ja')
    tts_ja.save("sample_ja.mp3")

    print("Combining audio into sample_mixed.mp3 without ffmpeg...")
    with open("sample_mixed.mp3", "wb") as out_f:
        for f in ["sample_vi.mp3", "sample_en.mp3", "sample_ja.mp3"]:
            with open(f, "rb") as in_f:
                out_f.write(in_f.read())
            os.remove(f)

    print("Done! Created sample_mixed.mp3")

if __name__ == "__main__":
    main()
