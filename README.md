# NOOBRA — Personal AI Desktop Agent

NOOBRA is a friendly Windows 11 desktop AI agent. It understands
**Roman Urdu + English**, opens apps, manages files, searches the web,
and remembers your preferences — using free-tier AI only
(Gemini `gemini-3.8-flash`, Groq `openai/gpt-oss-20b`, optional
OpenRouter). No Ollama, no local LLM, no paid APIs.

> Assalam-o-Alaikum! Main NOOBRA hoon — aapka personal AI agent. 😊

## Install (Windows 11)

1. **Install Python 3.11+** from https://www.python.org/downloads/
   — tick **"Add python.exe to PATH"** during setup.
2. **Clone the repo:**
   ```powershell
   git clone <repo-url>
   cd NOOBRA
   ```
3. **Create a virtual environment:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```
4. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   python -m playwright install chromium
   ```
5. **Set up your free API keys** — copy the example env file:
   ```powershell
   copy .env.example .env
   ```
   Then open `.env` in Notepad and paste your keys:
   - **Gemini (recommended, free):** https://aistudio.google.com/app/apikey
   - **Groq (free, fast fallback):** https://console.groq.com/keys
   - **OpenRouter (optional, free models):** https://openrouter.ai/keys
   - Set `NOOBRA_PROVIDER=gemini` (or `groq` / `openrouter`).
   - No key yet? NOOBRA still starts — the planner falls back to
     rule-based commands (e.g. "Chrome kholo") and tells you a key
     is needed for AI replies.
6. **Run it:**
   ```powershell
   python main.py
   ```

## Usage

| You say | NOOBRA does |
|---|---|
| `Chrome kholo` | Opens Chrome |
| `Desktop par Test folder banao` | Creates `Desktop\Test` |
| `Google par Python search karo` | Searches the web for Python |
| `Downloads organize karo` | Sorts Downloads into folders |
| `Mujhe yaad dilao ke main subah gym jata hoon` | Remembers the preference |

- **GUI:** type in the box and press **Send**, or press **🎤 Voice**.
  **Stop** cancels the running task. **⚙ Settings** changes the
  provider / models / keys (keys are never shown in plain text).
- **CLI mode:** `python main.py --cli` — type commands, `exit` to quit.
- **One shot:** `python main.py --text "Chrome kholo"`

## Keeping NOOBRA up to date

When a new fix is pushed to GitHub, update your PC copy like this:

**Manual (any time):** double-click `update.bat` in the NOOBRA folder,
or run `git pull` there. Restart NOOBRA afterwards to use the new code.

**Automatic (set up once):** in PowerShell, inside the NOOBRA folder:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-auto-update.ps1
```
This creates a Task Scheduler task ("NOOBRA Auto-Update") that runs
`update.bat` every 30 minutes while you are logged in. Remove it with:
`schtasks /Delete /TN "NOOBRA Auto-Update" /F`

Note: `update.bat` only works if the folder is a real Git clone, not a
ZIP extract. If it says "not a git repository", clone it once with
`gh auth login` then `gh repo clone Itx-Munawar/NOOBRA` (copy your
`.env` into the new folder first), and use that folder from then on.

## Build the .exe (Windows)

```powershell
pip install pyinstaller
pyinstaller noobra.spec
```

The app appears in `dist\NOOBRA\NOOBRA.exe`. Keep `.env` next to it
(or set the keys in Settings) — the `.exe` does not bundle your keys.

## Safety & permissions

NOOBRA classifies every tool call before running it
(`core/permissions.py`):

- **SAFE** (e.g. `open_app`) — runs immediately.
- **CAUTION** (e.g. `move_file`) — asks for your approval first.
- **DANGEROUS** (e.g. `delete_file`) — asks for explicit approval,
  and deletes go to the **Recycle Bin** (`send2trash`), never a
  permanent delete.
- Paths outside your allowed folders (e.g. `..`, `C:\Windows`) are
  blocked. API keys are never stored as a "preference" in memory
  and are never printed in logs.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Reinstall Python with "Add to PATH" ticked |
| GUI doesn't open | Run `python main.py --cli`; check PySide6 installed (`pip install PySide6`) |
| `429 / quota` error | Free-tier limit hit — NOOBRA falls back to the next provider with a key; wait a minute or switch provider in Settings |
| Playwright browser missing | `python -m playwright install chromium` |
| Voice doesn't work | Voice is optional — install the voice group in `requirements.txt` and check your mic; typing always works |

## Linux note

NOOBRA targets Windows 11. On Linux it still runs: `python main.py`
falls back to the CLI when PySide6 / a display is missing, and the
test suite runs on Linux (`pytest`). Windows-only features (desktop
automation, system apps) degrade gracefully instead of crashing.

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

Tests use mocks and `tmp_path` only — no real API keys, no real
browser, no real user files.
