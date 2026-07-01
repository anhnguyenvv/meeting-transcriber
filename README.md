# 🎙️ Offline Multilingual Meeting Transcriber & Summarizer

An enterprise-grade, fully **offline and local** meeting transcription, speaker diarization, and summarization assistant. Built with privacy-first engineering, this application integrates cutting-edge local AI models (**Faster-Whisper**, **Pyannote Audio**, and **Ollama Qwen2.5**) to capture, transcribe, align, translate, and summarize meetings with zero cloud dependency.

---

## 🏗️ System Architecture & Deep-Dive

For a detailed breakdown of the system architecture, data flow, tech stack decisions, technical challenges (like smart ducking and temporal alignment), and MLOps monitoring, please refer to our detailed documentation:

👉 **[Architecture & Deep-Dive Documentation](docs/architecture.md)**

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.11**
- **Ollama** (locally installed and serving)
- **NVIDIA GPU** with CUDA support is highly recommended for faster Whisper/Pyannote execution.

### Installation & Run

1. Clone the repository and navigate into the folder:
   ```bash
   cd meeting-transcriber
   ```
2. Set up the virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   
   pip install -r requirements.txt
   ```
3. Copy the environment template and insert your **Hugging Face Hub Token** (needed to download Pyannote Models):
   ```bash
   # Windows:
   copy .env.example .env
   # macOS/Linux:
   cp .env.example .env
   ```
   *Edit `.env` and fill in `HF_TOKEN`.*
4. Pull the local LLM model using Ollama:
   ```bash
   ollama pull qwen2.5:7b-instruct
   ```
5. Start the web server:
   ```bash
   python app.py
   ```
6. Open your browser and navigate to `http://localhost:7860`.

---

## 📄 License
This project is open-source and licensed under the **MIT License**.
Third-party models (Whisper, Pyannote, Qwen2.5) are subject to their respective licenses.
