import os
import json
from pathlib import Path
from typing import Dict, Any, List

def get_monitoring_stats(outputs_dir: str | Path = "outputs") -> Dict[str, Any]:
    outputs_path = Path(outputs_dir)
    if not outputs_path.exists():
        return {}

    total_meetings = 0
    total_duration_s = 0.0
    total_pipeline_s = 0.0
    
    # Latency accumulators for each step
    step_times = {
        "conversion": 0.0,
        "transcription": 0.0,
        "diarization": 0.0,
        "alignment": 0.0,
        "translation": 0.0,
        "summarization": 0.0
    }
    
    step_counts = {k: 0 for k in step_times.keys()}
    languages = {}
    rtf_list = []
    
    # Iterate through all run output directories
    for folder in outputs_path.iterdir():
        if not folder.is_dir():
            continue
            
        meta_file = folder / "metadata.json"
        if not meta_file.exists():
            continue
            
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue
            
        total_meetings += 1
        total_duration_s += meta.get("duration_s", 0.0)
        
        lang = meta.get("language", "unknown")
        languages[lang] = languages.get(lang, 0) + 1
        
        metrics = meta.get("metrics", {})
        if metrics:
            total_pipeline_s += metrics.get("total_time_s", 0.0)
            if "rtf" in metrics:
                rtf_list.append(metrics["rtf"])
                
            # Accumulate step timings
            mapping = {
                "conversion": "conversion_time_s",
                "transcription": "transcription_time_s",
                "diarization": "diarization_time_s",
                "alignment": "alignment_time_s",
                "translation": "translation_time_s",
                "summarization": "summarization_time_s"
            }
            
            for step_key, meta_key in mapping.items():
                if meta_key in metrics:
                    step_times[step_key] += metrics[meta_key]
                    step_counts[step_key] += 1

    if total_meetings == 0:
        return {}

    # Calculate averages
    avg_rtf = sum(rtf_list) / len(rtf_list) if rtf_list else 0.0
    
    avg_step_times = {}
    for step_key, total_time in step_times.items():
        count = step_counts[step_key]
        avg_step_times[step_key] = round(total_time / count, 2) if count > 0 else 0.0
        
    total_avg_step_time = sum(avg_step_times.values())
    step_shares = {}
    for step_key, avg_time in avg_step_times.items():
        step_shares[step_key] = round((avg_time / total_avg_step_time * 100), 1) if total_avg_step_time > 0 else 0.0

    return {
        "total_meetings": total_meetings,
        "total_duration_hours": round(total_duration_s / 3600, 2),
        "total_duration_mins": round(total_duration_s / 60, 2),
        "total_duration_s": round(total_duration_s, 2),
        "total_pipeline_s": round(total_pipeline_s, 2),
        "average_rtf": round(avg_rtf, 4),
        "average_step_times_s": avg_step_times,
        "step_shares_pct": step_shares,
        "language_distribution": languages
    }

def print_cli_report():
    stats = get_monitoring_stats()
    if not stats:
        print("No monitoring data found. Process some meetings first!")
        return
        
    print("=" * 60)
    print("   MEETING TRANSCRIBER PERFORMANCE MONITORING REPORT   ")
    print("=" * 60)
    print(f"Total Meetings Processed:       {stats['total_meetings']}")
    print(f"Total Audio Transcribed:        {stats['total_duration_mins']} mins ({stats['total_duration_hours']} hours)")
    print(f"Average Real-Time Factor (RTF): {stats['average_rtf']:.4f}")
    
    print("\nLanguage Distribution:")
    for lang, count in stats['language_distribution'].items():
        print(f"  - {lang.upper()}: {count} meetings")
        
    print("\nAverage Latency & Contribution per Pipeline Step:")
    print(f"  {'Step':<15} | {'Avg Latency (s)':<15} | {'Percentage (%)':<15}")
    print("  " + "-" * 51)
    for step, val in stats['average_step_times_s'].items():
        share = stats['step_shares_pct'][step]
        print(f"  {step.capitalize():<15} | {val:<15.2f} | {share:<15.1f}")
    print("=" * 60)

if __name__ == "__main__":
    print_cli_report()
