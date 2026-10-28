# Community results

Results people have shared with `llmbench share` (see [Share your results](README.md#share-your-results)).
Each row is one run of the built-in `gap-analysis` task, cold start, with the machine in normal use unless
the notes say otherwise. One run is an anecdote, not a measurement; differences under about 10 % are noise.

| Date | Machine | Server | Model | Wall | Gen tok/s | Quality | Gaps found | Min free | Rest of machine | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-28 | Apple M1 Pro, 32 GB | Ollama 0.40.11 | qwen3:8b | 763 s | 16.3 | FAIL (hit token limit) | – | 53 % | comfortable | [example](examples/m1pro-32gb/) |
| 2026-10-28 | Apple M1 Pro, 32 GB | Ollama 0.40.11 | qwen3:14b | 141 s | 11.1 | PASS | 3/4 | 41 % | comfortable | [example](examples/m1pro-32gb/) |
| 2026-10-28 | Apple M1 Pro, 32 GB | Ollama 0.40.11 | Qwen3.6-35B-A3B UD-Q3_K_XL | 273 s | 25.5 | PASS | 4/4 | 10 % | comfortable | [example](examples/m1pro-32gb/) |
