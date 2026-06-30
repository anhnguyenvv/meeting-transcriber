import numpy as np
from faster_whisper import WhisperModel
model = WhisperModel('tiny', device='cpu')
audio = np.zeros(16000, dtype=np.float32)
info = model.detect_language(audio)
print(info)
print(hasattr(info, "all_language_probs"))
