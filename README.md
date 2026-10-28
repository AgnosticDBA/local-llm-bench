# local-llm-bench

**Will this model run on my machine, and can I trust what it says?**

Most local-LLM benchmarks answer one question: how many tokens per second. That's the least useful
number when you are choosing a model for a laptop you also work on. `llmbench` measures three things in
one run, on your hardware, with your normal apps open:

1. **Speed.** Wall time, load, prefill and generation tokens per second, from a cold start.
2. **What it costs the rest of the machine.** Free memory and swap traffic, sampled every 2 seconds
   before, during and after the request. A model that "fits" can still push everything else into swap.
3. **Whether the answer holds up.** The bundled task asks the model to quote its sources word for word,
   and the tool checks every quote against the documents. Then it checks judgement: the documents have
   known answers and two traps, so a model that quotes faithfully but reasons badly fails too.

It needs only Python 3.9+ and a model server: [Ollama](https://ollama.com) or anything with an
OpenAI-compatible API (llama.cpp's `llama-server`, LM Studio, vLLM, `mlx_lm.server`). It has no Python
dependencies and sends nothing anywhere except to the server you point it at.

> **Why it exists:** I wanted to know whether a 32 GB M1 Pro could take over an hourly job from a CPU-only
> mini-PC. The fastest model on the Mac was also the one that pushed 35 GiB through swap in four
> minutes; the two smallest models were quick and confidently wrong. The whole story, with numbers, is in
> [docs/FINDINGS.md](docs/FINDINGS.md).
>
> **Run it on your machine and [share the numbers](#share-your-results).** One laptop is an anecdote;
> fifty are a buyer's guide. Shared results are collected in [RESULTS.md](RESULTS.md).

## Quick start

```bash
git clone https://github.com/AgnosticDBA/local-llm-bench.git
cd local-llm-bench
ollama pull qwen3:8b
python3 -m llmbench run -m qwen3:8b
```

Compare several models in one report (each one runs cold, one after another):

```bash
python3 -m llmbench run -m qwen3:8b -m qwen3:14b -m hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q3_K_XL
```

Or install it as a command with `pip install .`, then run `llmbench run -m qwen3:8b`.

Leave your usual apps open. The point is to see how the model behaves on the machine as you actually
use it, not on a freshly rebooted one.

## What you get

A line per run while it works, then a table, plus a folder `runs/<timestamp>/` holding:

| File | Contents |
|---|---|
| `report.html` | Self-contained page: wall-time chart (failed runs faded), results table, a memory timeline per run |
| `report.md` | The same table in Markdown. Private, like `results.json`: it shows paths, error text and the time of day. To post a result, use [`llmbench share`](#share-your-results). |
| `results.json` | Everything: machine, settings, timings, the model's parsed answer, kept and dropped items, raw memory samples |

Real output from a 32 GB M1 Pro with my usual apps open (about 8 GB in use when it started):

```text
$ python3 -m llmbench run -m qwen3:8b -m qwen3:14b -m hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q3_K_XL
machine: Apple M1 Pro (8P+2E cores), 32 GB RAM, Apple GPU (unified memory), macOS 26.6.2
backend: ollama 0.40.11 at http://127.0.0.1:11434
task:    gap-analysis

> qwen3:8b
  preflight: needs ~7.1 GB, other apps use ~8.6 GB now -> fits (headroom 16.3 GB)
  763 s, 16.3 tok/s, FAIL (no JSON object), machine comfortable

> qwen3:14b
  preflight: needs ~11.4 GB, other apps use ~8.0 GB now -> fits (headroom 12.6 GB)
  141 s, 11.1 tok/s, PASS, machine comfortable

> hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q3_K_XL
  preflight: needs ~20.5 GB, other apps use ~8.0 GB now -> tight (headroom 3.5 GB)
  273 s, 25.5 tok/s, PASS, machine comfortable
```

| Model | Wall | Prefill tok/s | Gen tok/s | Tokens | Kept | Dropped | Judgement | Quality | Min free | Swap in / out | Peak swap | Rest of machine |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3:8b | 763 s | 220 | 16.3 | 12288 | – | – | – | FAIL | 53 % | 0.2 / 0.0 GB | 17 MB/s | comfortable |
| qwen3:14b | 141 s | 109 | 11.1 | 1367 | 5 / 3 | 1 | 3/4 gaps | PASS | 41 % | 0.0 / 0.0 GB | 1 MB/s | comfortable |
| Qwen3.6-35B-A3B UD-Q3_K_XL | 273 s | 394 | 25.5 | 6669 | 5 / 6 | 0 | 4/4 gaps | PASS | 10 % | 0.0 / 0.4 GB | 137 MB/s | comfortable |

What that run shows:

- **The smallest model was the slowest.** qwen3:8b spent its whole 12,288-token budget reasoning
  (49,000 characters of it) and never wrote an answer. It took 763 s and returned nothing usable.
- **The 14B passed, narrowly.** It missed the SQL Server gap, and one "quote" had the version numbers
  quietly removed (`PostgreSQL 9.6–11 clusters` became `PostgreSQL clusters`), so the check dropped it.
- **The 35B mixture-of-experts at 3 bits gave the best answer.** It found all four gaps, saw through
  both traps ("only wrote a business case for retiring SQL Server... no direct administration experience"),
  and was the fastest of the three at generating, because only ~3 B of its 35 B parameters are active per token. It took
  the Mac down to 10 % free memory but swapped almost nothing. It was not flawless: it also listed
  incident response and mentoring as soft gaps, which the CV arguably covers. The keyword check does not
  score those; reading the answer does.

The full report for that run is in [`examples/m1pro-32gb/`](examples/m1pro-32gb/). GitHub shows
`report.md` directly; download `report.html` to see the charts.

### Reading the columns

| Column | Meaning |
|---|---|
| Wall | Seconds from sending the request to the last token. This is what you wait. |
| Prefill tok/s | How fast the prompt is read. It dominates for long documents. |
| Gen tok/s | How fast the answer, including any reasoning, is written. |
| Kept | Items whose quotes were found word for word, per list (here: strengths / gaps). |
| Dropped | Items with a quote that is not in the source: invented, paraphrased or misattributed. |
| Judgement | Known gaps the model found, out of those planted, plus any requirement it got backwards (a met requirement listed as a gap, or a gap listed as a strength). |
| Quality | **PASS** if at least 2 strengths and 1 gap survive, at least 60 % of items are kept, at least 3 of the 4 known gaps are found, nothing is backwards, and no more than 8 strengths and 8 gaps are listed (listing every requirement is not an answer). |
| Min free | Lowest free memory during the request (macOS `memory_pressure`, Linux `MemAvailable`). |
| Swap in / out | Data the OS read back from swap, and pushed out to it, during the request. Pushing your other apps out is a cost too. |
| Peak swap | The fastest swap traffic between two samples. Over 500 MB/s, the machine stalls. |
| Rest of machine | Swap moved in both directions during the request, plus how much swap grew. **comfortable**: under 1 GB · **swapping**: 1–8 GB · **thrashing**: over 8 GB, or over 500 MB/s at any point. These thresholds are judgement calls. |

Before each run it also prints a **preflight** estimate: the model's size plus about 15 % and 1.5 GB for
context and runtime, against what your other apps are using right now. Then it says *fits*, *tight*,
*will swap* or, on Apple Silicon, *too big for the GPU* (macOS lets the GPU use about 75 % of RAM by
default). The measurement afterwards tells you whether the estimate was right. On macOS it tends to be
optimistic, because "free" includes cache the OS can reclaim, and reclaiming it is exactly the cost you are
measuring.

## Options worth knowing

```text
-m MODEL            model to test; repeat for several
-t TASK             built-in task name or a path to your own task folder (default gap-analysis)
--repeat N          runs per model, each from a cold start (default 1; use 3 before trusting a gap under ~10 %)
--max-swap-gb N     stop a run if swap grows by more than N GB (default 16; 0 = never)
--num-ctx N         context window override
-o key=value        model option, e.g. -o temperature=0 -o think=false
--backend openai    talk to an OpenAI-compatible server instead of Ollama
--url URL           server address (default http://127.0.0.1:11434, or http://127.0.0.1:8080/v1 for openai)
```

Other commands: `llmbench share` writes a version of a run that is safe to post ([below](#share-your-results)).
`llmbench sysinfo` shows what the tool sees (chip, RAM, current memory and swap).
`llmbench tasks` lists the built-in tasks. `llmbench report runs/<timestamp>` re-renders a report.

### With llama.cpp, LM Studio or MLX

```bash
llama-server -m Qwen3.6-35B-A3B-UD-Q3_K_XL.gguf -c 16384 --port 8080 &
python3 -m llmbench run --backend openai -m qwen3.6-q3
```

Two differences from Ollama: the tool cannot unload the model between runs (restart the server for a cold
start), and it cannot read the model's size, so there is no preflight estimate.

## The bundled task

`gap-analysis` gives the model a fictional job posting and a fictional CV (both in
[`llmbench/tasks/gap-analysis`](llmbench/tasks/gap-analysis); about 1,400 prompt tokens). It asks for a
fit percentage, the strongest matches and the gaps, as JSON, with every requirement quoted from the posting
and every piece of evidence quoted from the CV. The documents were written with known answers. The
candidate has no SQL Server, Kafka/Debezium, Kubernetes operator or Dutch experience, and comfortably meets
the PostgreSQL, Patroni, AWS, Terraform and on-call requirements. Two lines are traps: the CV *mentions*
SQL Server (a business case, not administration) and Dutch (a beginner's course, not a working knowledge).
Quoting either as a strength is faithful to the text and still wrong. The `judgement` rules in `task.json`
catch exactly that: keyword lists of what the gaps must include, and what neither list may get backwards.

Why both checks? The first version of this task had only the quote check, and every model passed it,
including two that had failed the same kind of task on real, messier documents. Short, tidy bullet lists are
easy to copy from. A benchmark everything passes tells you nothing.

The quote check normalises case, whitespace, curly quotes and Markdown bullets, accepts a quote shortened
with `...` if the pieces appear in order within one paragraph or bullet and each piece is at least 12
characters, and rejects quotes under 12 characters ("PostgreSQL" proves nothing). The same item listed
twice counts once.

## Your own task

A task is a folder with a `task.json` and the source files it names:

```json
{
  "name": "contract-review",
  "description": "Find the termination clauses in a contract",
  "sources": {"contract": "contract.md"},
  "system": "Quote the contract word for word. Reply with one JSON object.",
  "user": "CONTRACT:\n\n{contract}\n\nReturn {\"clauses\": [{\"quote\": \"...\", \"summary\": \"...\"}]}",
  "options": {"temperature": 0.2, "num_ctx": 16384},
  "checks": {"clauses[].quote": "contract"},
  "gate": {"min_kept": {"clauses": 2}, "min_kept_ratio": 0.6, "min_found": 1, "max_wrong": 0},
  "judgement": {"clauses": {"field": "quote", "must_include": ["terminate"], "must_exclude": ["renewal"]}}
}
```

`{contract}` in the prompt is replaced with the file's text. Each `checks` entry says that field, in every
item of that list, must be a verbatim quote from that source. `judgement` is optional: for each list, the
keywords that some kept item must contain (`must_include`, counted against `min_found`) and must not
(`must_exclude`, counted against `max_wrong`). Run it with `-t path/to/folder`. Tasks with
checkable output make better benchmarks than tasks you can only eyeball, so if you can phrase yours as
"quote the evidence", do.

## Share your results

Results from other machines are the most useful thing this project can collect. They are what turn
"a 32 GB M1 Pro did this" into "here is what 16, 32, 48 and 64 GB actually buy you".

```bash
python3 -m llmbench share            # the newest run; or: python3 -m llmbench share runs/<timestamp>
```

This writes `share.md` next to the run and prints all of it, so you see exactly what would go out. Then
[open a "Share a result" issue](https://github.com/AgnosticDBA/local-llm-bench/issues/new?template=share-result.yml)
and paste it in.

**What `share` keeps, and what it never does.** It works from an allow-list: a field gets in only if the
code names it.

| Shared | Never shared |
|---|---|
| Date (no time of day) | The model's answers and reasoning |
| Chip, cores, RAM, GPU type, OS name and major version | Source documents or any quote from them |
| Model server and version | File paths, usernames, the server URL |
| Model names (a file path becomes just the file name) | Error messages (only "there was an error") |
| Timings, token counts, pass/fail, kept/dropped/gaps-found counts | The second-by-second memory timeline |
| Memory summary: lowest free %, swap moved, verdict | Anything about a custom task except a fingerprint |

- **Custom tasks are refused by default.** Their names, keywords and quotes may be private. A task folder
  you add to, or edit inside, `llmbench/tasks/` counts as custom too: "built-in" means byte-for-byte the
  files this version shipped with.
  `--include-custom-task` shares the numbers with the task shown only as `custom` plus a 12-character
  fingerprint, so two people can tell they ran the same task without revealing it. Anyone who can guess
  your task files exactly can also use it to confirm the guess, so if the task itself is the secret, keep
  the run to yourself.
- **The one thing it cannot judge is your model names.** If you test a private fine-tune, rename it in
  `share.md` before posting.
- **A GitHub issue shows your username.** Nothing in the share output identifies you; the account you post
  from does. Using a separate account is fine.
- **Posted something by mistake?** Editing does not remove it (GitHub keeps edit history). Report it
  privately via [SECURITY.md](SECURITY.md) and I will delete the issue. Deleting cannot recall the
  notification emails GitHub has already sent, or copies in public archives of GitHub activity, so read
  `share.md` before you post rather than after.

If someone sends you a share file directly, `llmbench share --verify share.md` checks that the whole file
is laid out exactly as the tool writes it: no extra fields, values of the allowed shape, nothing added around
the JSON. Hardware names are free text, so read them; the check cannot prove the numbers are honest. Never post or forward `results.json`: it holds the full answers.

## Limitations

- One task out of the box, and **one run per model unless you ask for more**. Differences of a few percent
  are noise.
- The judgement check is keyword-based: it knows which requirements are gaps, not whether the model's
  notes about them are sensible. Read a few answers in `results.json` yourself.
- Memory sampling works on macOS and Linux. On Windows the run works, but the memory columns are empty.
- The memory watchdog stops a request between streamed chunks. During a long prefill no chunks arrive, so
  it can only ask the server to unload the model (Ollama) and wait; how quickly a server gives up an
  in-flight request then is up to the server. With `--backend openai` it cannot even do that.
- With `--backend openai`, a server that reports no token usage gets its tokens counted as streamed chunks,
  which is close to, but not exactly, the token count.
- GPU memory on discrete cards (NVIDIA) is not sampled yet; the RAM and swap figures still show spill-over.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Licence

MIT. See [LICENSE](LICENSE).
