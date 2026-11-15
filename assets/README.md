# NOOBRA assets

This folder holds icons and orb artwork for the desktop app.

**Nothing is bundled yet.** The animated orb in the UI is drawn
programmatically (`ui/components.py` — `AnimatedOrb` with a real
`QTimer` + `QPainter` gradient pulse), so the app does not depend on
any image files.

When icons are added later, place them here (e.g. `noobra.ico` for
the Windows executable / taskbar icon) and reference them from
`noobra.spec` / `ui/main_window.py`.
