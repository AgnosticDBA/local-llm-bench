# local-llm-bench: gap-analysis

> **Private.** This report shows model names, paths, error text and the time of day. To post a result, run `llmbench share` and post `share.md` instead.

**Machine:** Apple M1 Pro (8P+2E cores), 32 GB RAM, Apple GPU (unified memory), macOS 26.6.2  
**Backend:** ollama 0.40.11  
**Started:** 2026-10-28 18:28:20 CET

| Model | Wall | Prefill tok/s | Gen tok/s | Tokens | Kept | Dropped | Judgement | Quality | Min free | Swapped in | Rest of machine |
|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3:8b | 763 s | 220 | 16.3 | 12288 | – | – | – | FAIL | 53 % | 0.2 GB | comfortable |
| qwen3:14b | 141 s | 109 | 11.1 | 1367 | 5 / 3 | 1 | 3/4 gaps | PASS | 41 % | 0.0 GB | comfortable |
| hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q3_K_XL | 273 s | 394 | 25.5 | 6669 | 5 / 6 | 0 | 4/4 gaps | PASS | 10 % | 0.0 GB | comfortable |

Notes:
- **qwen3:8b**: no JSON object

*Kept* = items whose quotes were found word for word in the sources (per list, in task order). *Rest of machine*: swap moved in and out plus swap growth: comfortable < 1 GB; swapping 1–8 GB; thrashing > 8 GB or > 500 MB/s.
