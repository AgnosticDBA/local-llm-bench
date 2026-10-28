# Security and privacy

`llmbench` runs on your machine and talks only to the model server you point it at. It sends nothing
anywhere else, and it has no telemetry.

## What stays on your machine

`runs/<timestamp>/results.json` holds everything from a run, including the model's full answers. For the
built-in task those answers quote fictional documents. For a task of your own they quote *your* documents.
Treat `results.json`, `report.md` and `report.html` as private. `llmbench run` writes a `.gitignore` containing `*` into every run folder,
so run output stays out of git whichever directory you run it from.

## What is safe to share

`llmbench share` writes `share.md` from an allow-list. A field gets in only if the code names it:

- the date (no time of day), chip, core count, RAM, GPU type, OS name and major version;
- the model server, its version, and each model's name, timings and token counts;
- counts from the quality check (kept, dropped, gaps found) and the memory summary.

It never includes the model's answers or reasoning, source text, file paths, the server URL, error messages
or the memory timeline. A model given as a file path keeps only its file name. A run on a custom task is
refused unless you pass `--include-custom-task`. Even then the task appears only as `custom` plus a
12-character fingerprint of its files, never their names or content.

If you receive a share file, `llmbench share --verify share.md` checks the whole file is exactly what the tool would have
written. It checks the file's shape; it cannot prove the numbers are honest.

## Reporting a problem

If `share` lets something private through, or you posted something here by mistake, report it **privately**
through
[GitHub's private vulnerability reporting](https://github.com/AgnosticDBA/local-llm-bench/security/advisories/new).
Please do not open a public issue for it. Editing a post does not remove the old text (GitHub keeps the edit
history), and only the maintainer can delete an issue, so ask for deletion. Deletion removes the issue
from GitHub; it cannot recall notification emails already sent, or copies in public archives of GitHub
activity. You can delete your own comments
yourself. Reports are read by one person; expect a reply within days, not hours.
