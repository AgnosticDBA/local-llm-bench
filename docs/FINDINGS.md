# What one afternoon of measuring taught me about local LLMs on a 32 GB Mac

This tool exists because of one question: **could my 32 GB M1 Pro MacBook take over a job that an
Intel mini-PC was doing on its CPU, without making the laptop unusable?** The job is real and runs
every hour: a model reads a job posting and a CV, then writes a gap analysis whose every claim must quote
both documents word for word. It's a good test because it is long (about 5,000 prompt tokens and
6,000 generated tokens, with reasoning) and because the output can be *checked*, not just read.

Everything below comes from that real job, run once per configuration on 2026-10-28. The CV and the
posting are private, so the repository ships a fictional pair of the same shape
(`llmbench/tasks/gap-analysis`) and you can reproduce the *method*, not my exact numbers.

## The machines

| | Intel mini-PC | MacBook Pro |
|---|---|---|
| Chip | Core i9-12900H, 20 threads | Apple M1 Pro, 8P+2E CPU, 16-core GPU |
| Memory | 64 GB (≈61 GiB visible to Linux) | 32 GB unified |
| Accelerator | none usable; CPU inference | GPU, sharing the same 32 GB |
| Runtime | Ollama 0.35, GGUF | Ollama 0.40 (MLX and llama.cpp runners) |
| Everything else running | a few services | a normal working day: browser with many tabs, chat and coding apps, ~22 GB in use |

## Results

| Machine | Model and build | Size | Wall time | Generation | Quotes verified / dropped | Rest of the machine |
|---|---|---|---|---|---|---|
| Mini-PC (CPU) | Qwen3.6 35B-A3B, Q4_K_M GGUF | 22 GB | 620 s | 9.9 tok/s | 5 / 3 | untouched, no swap |
| Mini-PC (CPU) | Gemma 4 26B, Ollama default | 18 GB | 548 s | 8.1 tok/s | 5 / 3 | untouched, no swap |
| M1 Pro | Qwen3 8B | 5.2 GB | 111 s | 13.8 tok/s | **1 / 7** | no swap¹ |
| M1 Pro | Qwen3 14B | 9.3 GB | 173 s | 9.1 tok/s | **6 / 6**, every strength filed as a gap | no swap |
| M1 Pro | Qwen3.6 35B-A3B, MLX nvfp4 | 23 GB | **220 s** | **33.4 tok/s** | 3 / 5 | **thrashing**: 1–4 % free for the whole run, ≈35 GiB swapped in and ≈39 GiB out in 4 minutes, up to 1.1 GB/s |
| M1 Pro | Qwen3.6 35B-A3B, unsloth UD-Q3_K_XL GGUF | 17 GB | 329 s | 20.8 tok/s | 7 / 3 | swapping, mildly: 9 % free at worst, ≈2 GiB swapped in, peak 251 MB/s |

¹ That run came straight after I had quit apps and run a memory-cleaner utility. It flattered the result;
the 14B retest was done with my usual apps open, and so was everything after it.

## Eight things I learned

**1. Speed means nothing without a quality gate.** The two fastest Mac runs, the 8B and 14B dense models,
returned well-formed, confident JSON. Read casually, both looked fine. Checked against the source
text, the 8B's quotes mostly did not exist, and the 14B put every strength in the gaps list. If I had
only timed them, I would have picked the wrong model. That is why the tool's quality check is
mechanical: a quote is either in the document or it is not.

**2. "It fits" is not a yes/no question.** The 23 GB MLX build loaded, ran on the GPU and was the
fastest generator of the day: 2.8× faster than the mini-PC end to end and 3.4× faster at generating.
It was also the worst for the laptop. Free memory sat at 1–4 % for four minutes while macOS pushed about
35 GiB through swap to make room. It finished, and memory recovered the moment the model unloaded, but
anything else I was doing would have crawled. A benchmark that reports only tokens per second hides
the cost that matters on a machine you also work on.

**3. On a 32 GB Mac, quantisation is the lever.** The same 35B-A3B model at 3 bits (17 GB) kept the
quality on this task, with more quotes verified than the 4-bit build, not fewer, though one run each is not
proof. It took half as long again as the 4-bit MLX build and still 1.9× faster than the mini-PC. It moved
about **17× less data through swap**. It is the only configuration that suits a 32 GB laptop alongside a
normal desktop.

**4. Mixture-of-experts suits bandwidth-limited hardware.** Qwen3.6 35B-A3B has 35 B parameters but only
about 3 B are active per token, so each token reads a fraction of the weights. On the mini-PC an earlier
test found the MoE ahead of a dense 8B at every prompt size. I did not measure the dense 27B Qwen3.6 here;
on paper it reads all 27 B parameters per token, so on the same memory bandwidth it would generate several
times slower.

**5. Measure with your real desktop open, and cold.** The memory-cleaner run in note ¹ is one trap.
The other is warm caches: a model that is already loaded, or a server that has cached the prompt,
makes prefill look instant. (One of my mini-PC runs reported no prefill time at all for exactly that reason.)
The tool unloads the model before every run so each run starts cold.

**6. Give the test an off switch.** One early attempt at the 23 GB model was stopped by a watchdog
after 12 seconds, when swap passed 10 GB. That was deliberate: a benchmark that can lock up the
machine you are using needs a limit. `llmbench` stops a run when swap grows more than `--max-swap-gb`
(16 GB by default) and records why.

**7. Apple Silicon has a GPU ceiling below your RAM.** By default macOS lets the GPU wire roughly 75 %
of unified memory; on the 32 GB machine Ollama reported about 25 GiB usable. A model plus its context that
needs more will not run fully on the GPU however much you close.

**8. A benchmark everything passes tells you nothing.** When I rebuilt the test with fictional documents
for this repository, every model passed the quote check, including the two that had failed on the real
documents. Clean bullet lists are easy to copy from; a real posting is prose. So the bundled task now has
known answers and two traps (a CV line that *mentions* SQL Server without showing admin experience, and a
beginner's Dutch course), and the tool grades whether the model found the real gaps. See the README for
what that version measured.

## So what should you buy?

For *this* class of model, a ~35B MoE at 3–4 bits, which is today's sweet spot for local quality. The
32 GB row is measured; the 48 and 64 GB rows are extrapolated from it, and are what shared results can
confirm or correct:

| Unified memory | What it means |
|---|---|
| 32 GB | Works with the 3-bit build (≈17 GB) next to a normal desktop, with some swap. The 4-bit build (≈23 GB) runs but thrashes unless you close almost everything. |
| 48 GB | The 4-bit build plus a normal working day: ≈22 GB of apps + ≈23–25 GB of model. The practical minimum for "run it while I work". |
| 64 GB | Comfortable: room for longer contexts, a second model, or the 8-bit build. |

If you already have a CPU-only box with plenty of RAM, it is a perfectly good *background* engine:
slower, but it never touches your laptop.

## Caveats, stated plainly

- One task, one posting, **one run per configuration**. Treat differences under ~10 % as noise.
- On the real task the gate checked *faithfulness* only (are the quotes real?). The bundled task adds a
  keyword-based judgement check; neither grades the model's reasoning in full.
- Different runtimes (CPU GGUF, Apple MLX, llama.cpp on Metal) are part of each result; I compared
  "the best way to run it on that machine", not identical code paths.
- Memory figures come from macOS `vm_stat`, `memory_pressure` and `vm.swapusage`. They describe the whole
  machine, not just the model.
