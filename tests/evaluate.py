import os
import sys
import json
import time
import re
from pathlib import Path

# Ensure project root is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import transcribe
import soundfile as sf

def LevenshteinDistance(r, h):
    """
    Calculation of Levenshtein distance.
    Works for both lists (words) and strings (characters).
    """
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
        
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            if r[i - 1] == h[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                substitution = d[i - 1][j - 1] + 1
                insertion = d[i][j - 1] + 1
                deletion = d[i - 1][j] + 1
                d[i][j] = min(substitution, insertion, deletion)
    return d[len(r)][len(h)]

def normalize_text_en_vi(text):
    """Normalize English and Vietnamese text (lowercase, remove punctuation)."""
    text = text.lower()
    # Remove punctuation
    text = re.sub(r'[^\w\s]', '', text)
    # Remove multiple spaces
    text = " ".join(text.split())
    return text

def normalize_text_ja(text):
    """Normalize Japanese text (lowercase, remove punctuation and spaces)."""
    text = text.lower()
    # Remove punctuation and spaces
    text = re.sub(r'[^\w]', '', text)
    return text

def calculate_wer(ref, hyp):
    """Word Error Rate."""
    ref_norm = normalize_text_en_vi(ref)
    hyp_norm = normalize_text_en_vi(hyp)
    
    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()
    
    if not ref_words:
        return 1.0 if hyp_words else 0.0
        
    dist = LevenshteinDistance(ref_words, hyp_words)
    return dist / len(ref_words)

def calculate_cer(ref, hyp):
    """Character Error Rate."""
    ref_norm = normalize_text_ja(ref)
    hyp_norm = normalize_text_ja(hyp)
    
    if not ref_norm:
        return 1.0 if hyp_norm else 0.0
        
    dist = LevenshteinDistance(ref_norm, hyp_norm)
    return dist / len(ref_norm)

def main():
    samples_dir = Path(__file__).parent / "samples"
    gt_file = samples_dir / "ground_truth.json"
    
    if not gt_file.exists():
        print(f"Error: Ground truth file not found at {gt_file}.")
        print("Please run 'python tests/generate_test_data.py' first.")
        sys.exit(1)
        
    with open(gt_file, "r", encoding="utf-8") as f:
        ground_truths = json.load(f)
        
    results = {}
    total_audio_duration = 0.0
    total_processing_time = 0.0
    
    print("=" * 70)
    print(" STARTING PIPELINE ACCURACY & LATENCY EVALUATION ")
    print("=" * 70)
    
    table_rows = []
    
    for filename, ref_text in ground_truths.items():
        audio_path = samples_dir / filename
        if not audio_path.exists():
            print(f"Skipping {filename}: audio file not found.")
            continue
            
        # Get audio duration
        info = sf.info(str(audio_path))
        duration = info.duration
        total_audio_duration += duration
        
        print(f"\nProcessing {filename} (Duration: {duration:.2f}s)...")
        
        # Measure time
        start_time = time.time()
        try:
            # Run Whisper transcription
            segments = transcribe.run(audio_path)
            hyp_text = " ".join([seg.text for seg in segments])
        except Exception as e:
            print(f"Error transcribing {filename}: {e}")
            continue
            
        elapsed_time = time.time() - start_time
        total_processing_time += elapsed_time
        
        # Calculate metric
        is_japanese = "ja" in filename
        if is_japanese:
            metric_name = "CER"
            score = calculate_cer(ref_text, hyp_text)
        else:
            metric_name = "WER"
            score = calculate_wer(ref_text, hyp_text)
            
        rtf = elapsed_time / duration if duration > 0 else 0
        
        results[filename] = {
            "duration_s": duration,
            "processing_time_s": elapsed_time,
            "rtf": rtf,
            "metric": metric_name,
            "accuracy_score": score,
            "reference": ref_text,
            "hypothesis": hyp_text
        }
        
        table_rows.append((
            filename,
            f"{duration:.1f}s",
            f"{elapsed_time:.1f}s",
            f"{rtf:.2f}",
            f"{metric_name}: {score*100:.1f}%"
        ))
        
        print(f"Reference:  {ref_text}")
        print(f"Hypothesis: {hyp_text}")
        print(f"Time: {elapsed_time:.2f}s | RTF: {rtf:.2f} | {metric_name}: {score*100:.1f}%")
        
    # Print summary table
    print("\n" + "=" * 70)
    print(f"{'Filename':<20} | {'Duration':<8} | {'Latency':<8} | {'RTF':<6} | {'Error Rate':<12}")
    print("-" * 70)
    for row in table_rows:
        print(f"{row[0]:<20} | {row[1]:<8} | {row[2]:<8} | {row[3]:<6} | {row[4]:<12}")
    print("=" * 70)
    
    overall_rtf = total_processing_time / total_audio_duration if total_audio_duration > 0 else 0
    print(f"OVERALL SUMMARY:")
    print(f"- Total Audio Duration:   {total_audio_duration:.2f}s")
    print(f"- Total Processing Time:  {total_processing_time:.2f}s")
    print(f"- Average Real-Time Factor (RTF): {overall_rtf:.2f}")
    
    # Save report JSON
    report_json_path = Path(__file__).parent / "evaluation_report.json"
    report_data = {
        "overall": {
            "total_audio_duration_s": total_audio_duration,
            "total_processing_time_s": total_processing_time,
            "average_rtf": overall_rtf,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        },
        "details": results
    }
    
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    print(f"\nEvaluation report JSON saved to {report_json_path}")
    
    # Save report Markdown
    report_md_path = Path(__file__).parent / "evaluation_report.md"
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("# Japanese ASR Evaluation Report\n\n")
        f.write(f"**Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Overall Metrics\n")
        f.write(f"- **Total Audio Duration:** {total_audio_duration:.2f}s\n")
        f.write(f"- **Total Processing Time:** {total_processing_time:.2f}s\n")
        f.write(f"- **Average RTF:** {overall_rtf:.2f}\n\n")
        
        f.write("## Detailed Results\n")
        f.write("| Filename | Duration | Latency | RTF | Error Rate (CER/WER) |\n")
        f.write("|----------|----------|---------|-----|----------------------|\n")
        for row in table_rows:
            f.write(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |\n")
        
    print(f"Evaluation report Markdown saved to {report_md_path}")

if __name__ == "__main__":
    main()
