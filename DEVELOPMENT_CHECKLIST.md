# NOOBRA — Development Checklist

Milestones, what works, and what has been verified where.
"Linux" = verified in this Linux build environment (Python 3.12.3,
no PySide6 / display / Chrome / Playwright installed).
"Windows" = still needs verification on the target Windows 11 machine.

| # | Milestone | What works | Tested on Linux | Needs Windows verification |
|---|---|---|---|---|
| 1 | Project setup, dependencies, AI provider integration | Project skeleton, `core/config` settings, `.env` loading, Gemini / Groq / OpenRouter via free tiers, `RateLimitError` on 429, `AuthError` on 401, fallback chain skipping key-less providers | `python -m compileall`, `tests/test_providers.py` (mocked `requests.post`) | Real API calls with real free keys |
| 2 | Natural language, conversation, task planning | Rule-based Roman Urdu/English fallback (no key): Chrome open, folder create, web search; clarification for ambiguous deletes; LLM JSON planning when a provider is configured | `tests/test_planner.py`, `tests/test_integration.py` | Live planning with a provider |
| 3 | Windows application and file-system control | App launch/close, window listing, mouse/keyboard (guarded pyautogui), file create/copy/move/search/read, organize Downloads, duplicates, trash-only delete with confirmation, safe-path blocking | `tests/test_files.py`, `tests/test_permissions.py` | Real Desktop/Downloads paths, Chrome/VS Code launch, window switching |
| 4 | Chrome automation (Playwright) | `BrowserAgent`: launch (Chrome channel → Chromium), tabs, navigate, Google/YouTube search, read content, click/fill, download, back/forward | `tests/test_browser_mock.py` (mocked); real Playwright absent on Linux, so calls fail clearly with install instructions | Real Chromium launch and search on Windows |
| 5 | Autonomous execution, observation, verification | Agent loop: plan → permission check → execute → verify → report; SAFE-only retry, never retry delete/submit/send; cancellation via `threading.Event`; progress callbacks | `tests/test_integration.py` (end-to-end folder creation in a sandboxed HOME); `python main.py --text "Desktop par SmokeTest folder banao"` created the folder | Multi-step browser tasks on Windows |
| 6 | Voice, personality | faster-whisper STT, edge-tts TTS, wake-word listener, mute/stop, Roman Urdu replies in the user's language mix | Compile + graceful degradation (deps absent on Linux) | Microphone + speaker on Windows |
| 7 | Memory, security, permissions | SQLite memory (history/preferences/tasks/shortcuts), API keys refused as preferences, 3 permission levels, shell-command blocklist, prompt-injection detection, audit log (SQLite + file) | `tests/test_memory.py`, validator/audit smoke tests | Persistence across restarts, GUI approval prompts |
| 8 | Premium UI, integration testing, packaging | PySide6 dark theme (#121212, #00aaff, #8b5cf6), animated orb (real QTimer), chat, voice button, Stop, history, settings (provider/models/keys), QThread worker | `python -m compileall`; GUI cannot render without PySide6/display here | Full GUI run on Windows 11, orb animation, settings save, `pyinstaller noobra.spec` .exe build + run |

## Integration fixes (coordinator, 2026-11-15)

The four workstreams' per-module tests all passed (31/31) while the
end-to-end path was broken. Fixed during integration:

1. **Planner → registry mismatch (critical):** the planner emitted
   `search_google` / `search_youtube` / `navigate`, `open_app(app=...)`,
   `create_folder(path, name=...)`, `search_files(query=..., path=...)`,
   but the registry only had `browser_search` / `browser_navigate` and
   functions taking `name` / `directory` / `pattern`. Fixed the planner
   to emit registry-matching names/args, added `search_google`,
   `search_youtube` and `navigate` as registry aliases, and made
   `launch_app`/`open_app`/`close_app`/`is_app_running` accept an
   `app=` alias. Pinned by new `tests/test_integration.py`.
2. **Windows path allow-list bypass (security):**
   `is_path_allowed("C:\\Windows\\System32\\cmd.exe")` returned `True`
   on Linux (treated as a relative path under home). Fixed:
   Windows drive/UNC paths are now judged as Windows paths on any OS —
   blocked system dirs are rejected, only `X:\Users\<name>\...`
   profile paths are allowed, everything else on a drive fails closed.
   Pinned by an updated `tests/test_files.py`.
3. **Permissions:** added `browser_navigate` / `browser_search` /
   `browser_read` / `browser_new_tab` / `browser_back` /
   `browser_forward` / `launch_app` to the SAFE aliases (previously
   unknown tools failed closed to CAUTION and needed approval).

## Verification (2026-11-15, Linux, Python 3.12.3)

```bash
python -m compileall .            # COMPILE_OK
python -m pytest -q               # 36 passed, 0 failed
python main.py --text "Chrome kholo aur YouTube par Python tutorials search karo"
  # plans 2 steps; on Linux both fail clearly:
  # "Windows-only app on Linux: Google Chrome is not installed"
  # "Playwright not installed: pip install playwright && playwright install chromium"
python main.py --text "Desktop par SmokeTest folder banao"   # with sandboxed HOME: "Ho gaya!" + folder created
```

## How to verify (Windows)

```powershell
python -m pytest tests/ -v
python main.py --cli --text "Chrome kholo"
python main.py
pyinstaller noobra.spec
```

## Known limitations (Linux build env)

- PySide6, Playwright, Chrome and pyautogui are not installed here, so
  GUI / browser / desktop-automation code degrades gracefully instead
  of crashing; those paths need Windows verification.
- No real API keys were used or stored anywhere in this build; the
  planner's rule-based fallback is what was exercised end to end.
- `noobra.spec` was syntax-checked only; the `.exe` has not been built
  (PyInstaller build must run on Windows).

## Model fix (2026-11-15, after Windows test)

- Gemini `gemini-2.0-flash` returned HTTP 404 on Windows: "no longer
  available, use models/gemini-3.8-flash". Updated default to
  `gemini-3.8-flash` (GA Sep 2, 2026) in `ai/gemini.py`, `core/config.py`,
  `ui/settings.py`, `.env.example`, `README.md`.
- Groq `llama-3.3-70b-versatile` returned HTTP 404 / model_not_found.
  Groq moved both Llama models to Enterprise on Aug 16, 2026; free tier
  now includes `openai/gpt-oss-20b`. Updated Groq default to
  `openai/gpt-oss-20b` in `ai/groq.py`, `core/config.py`,
  `ui/settings.py`, `.env.example`, `README.md`.
- OpenRouter 401 "User not found" is a key problem, not a model problem:
  the key in the user's `.env` is invalid. Get a fresh key at
  https://openrouter.ai/keys, or leave OpenRouter blank and use Gemini/Groq.
- IMPORTANT for existing installs: `.env` overrides code defaults. Users
  with an old `.env` must edit `GEMINI_MODEL=` and `GROQ_MODEL=` in
  `.env` to the new names above (or delete those two lines so the new
  defaults apply).
