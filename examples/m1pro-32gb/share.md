**llmbench 0.1.0** · 2026-10-28 · Apple M1 Pro (8P+2E cores), 32 GB, macOS 26 · ollama 0.40.11 · task `gap-analysis`

| Model | Wall | Gen tok/s | Quality | Kept / dropped | Gaps found | Min free | Swap in / out | Peak swap | Rest of machine |
|---|---|---|---|---|---|---|---|---|---|
| qwen3:8b | 762.8 s | 16.3 | FAIL | 0 / 0 | – | 53.0 % | 0.2 / 0.0 GB | 16.7 MB/s | comfortable |
| qwen3:14b | 141.3 s | 11.1 | PASS | 8 / 1 | 3/4 | 41.0 % | 0.0 / 0.0 GB | 1.4 MB/s | comfortable |
| hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q3_K_XL | 273.2 s | 25.5 | PASS | 11 / 0 | 4/4 | 10.0 % | 0.0 / 0.4 GB | 136.8 MB/s | comfortable |

```json
{
 "llmbench_share": 1,
 "tool_version": "0.1.0",
 "date": "2026-10-28",
 "machine": {
  "cpu": "Apple M1 Pro",
  "cores": "8P+2E",
  "ram_gb": 32,
  "gpu": "Apple GPU (unified memory)",
  "arch": "arm64",
  "os": "macOS 26"
 },
 "backend": "ollama",
 "backend_version": "0.40.11",
 "task": {
  "name": "gap-analysis",
  "builtin": true
 },
 "runs": [
  {
   "model": "qwen3:8b",
   "repeat": 1,
   "metrics": {
    "wall_s": 762.8,
    "ttft_s": 9.4,
    "load_s": 3.1,
    "prompt_tokens": 1365,
    "prefill_tok_s": 219.7,
    "gen_tokens": 12288,
    "gen_tok_s": 16.3,
    "done_reason": "length",
    "error": false
   },
   "check": {
    "parsed": false,
    "passed": false,
    "kept": {},
    "dropped": 0,
    "gaps_found": null,
    "gaps_expected": null,
    "wrong": 0
   },
   "memory": {
    "free_pct_before": 74.0,
    "free_pct_min": 53.0,
    "free_pct_after": 75.0,
    "swap_used_mb_before": 4988.8,
    "swap_used_mb_peak": 4964.8,
    "swapped_in_mb": 228.5,
    "swapped_out_mb": 0.0,
    "peak_swap_mb_s": 16.7
   },
   "memory_verdict": "comfortable",
   "preflight": "fits"
  },
  {
   "model": "qwen3:14b",
   "repeat": 1,
   "metrics": {
    "wall_s": 141.3,
    "ttft_s": 18.1,
    "load_s": 5.3,
    "prompt_tokens": 1365,
    "prefill_tok_s": 108.9,
    "gen_tokens": 1367,
    "gen_tok_s": 11.1,
    "done_reason": "stop",
    "error": false
   },
   "check": {
    "parsed": true,
    "passed": true,
    "kept": {
     "strengths": 5,
     "gaps": 3
    },
    "dropped": 1,
    "gaps_found": 3,
    "gaps_expected": 4,
    "wrong": 0
   },
   "memory": {
    "free_pct_before": 75.0,
    "free_pct_min": 41.0,
    "free_pct_after": 75.0,
    "swap_used_mb_before": 4756.6,
    "swap_used_mb_peak": 4756.6,
    "swapped_in_mb": 14.1,
    "swapped_out_mb": 0.0,
    "peak_swap_mb_s": 1.4
   },
   "memory_verdict": "comfortable",
   "preflight": "fits"
  },
  {
   "model": "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q3_K_XL",
   "repeat": 1,
   "metrics": {
    "wall_s": 273.2,
    "ttft_s": 12.0,
    "load_s": 8.4,
    "prompt_tokens": 1422,
    "prefill_tok_s": 394.1,
    "gen_tokens": 6669,
    "gen_tok_s": 25.5,
    "done_reason": "stop",
    "error": false
   },
   "check": {
    "parsed": true,
    "passed": true,
    "kept": {
     "strengths": 5,
     "gaps": 6
    },
    "dropped": 0,
    "gaps_found": 4,
    "gaps_expected": 4,
    "wrong": 0
   },
   "memory": {
    "free_pct_before": 75.0,
    "free_pct_min": 10.0,
    "free_pct_after": 71.0,
    "swap_used_mb_before": 4724.6,
    "swap_used_mb_peak": 5104.6,
    "swapped_in_mb": 48.5,
    "swapped_out_mb": 380.0,
    "peak_swap_mb_s": 136.8
   },
   "memory_verdict": "comfortable",
   "preflight": "tight"
  }
 ]
}
```
