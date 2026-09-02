---
description: Sets up this project's virtual environment, installs dependencies, and prepares .env so it's ready to run. Use when the user asks to set up, install, or get this project running for the first time.
---

# Project Setup

Prepares this repo to run — creates the venv, installs dependencies, prepares `.env` — then hands the user the exact command to run it themselves. Never runs `python main.py` on the user's behalf; see the "Don't run it for them" note below.

## Steps

1. **Virtual environment**: if `venv/` doesn't already exist at the repo root, create it with `python -m venv venv`.
2. **Dependencies**: activate the venv for the user's actual shell (see `README.md`'s Setup section for the exact activation command per shell — Git Bash, PowerShell/cmd, macOS/Linux all differ), then run `pip install -r requirements.txt` inside it.
3. **`.env`**: if `.env` doesn't exist, copy it from `.env.example`.
4. **Token check**: read `.env` and check whether `GITHUB_PAT` is empty or still the placeholder. If so, stop and tell the user to create a token at https://github.com/settings/tokens (no special scopes needed for public repos) and paste it into `.env` themselves. Never ask the user to paste a secret into the chat, and never fill in or invent a token yourself.
5. Once dependencies are installed and a real token is present, report what was done and give the user the exact copy-pasteable commands for their shell to activate the venv and run the pipeline.

## Don't run it for them

Stop after handing back the commands — do not execute `python main.py`. This project's stated convention (see `ai_utils/README.md`) is that the user runs the pipeline themselves rather than an agent running it on their behalf, since a run takes a couple of minutes and hits the live GitHub API under their own token.
