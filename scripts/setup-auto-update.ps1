# NOOBRA — Set up automatic updates (Windows)
#
# Run this ONCE from PowerShell, inside the NOOBRA folder:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup-auto-update.ps1
#
# What it does:
# - Creates a Windows Task Scheduler task called "NOOBRA Auto-Update"
#   that runs update.bat --silent every 30 minutes (only when you are
#   logged in, and only when the PC is on and online).
# - Does NOT update NOOBRA right now — double-click update.bat for that,
#   or wait for the next scheduled run.
#
# To remove the automatic task later, run:
#   schtasks /Delete /TN "NOOBRA Auto-Update" /F
# To check it:  schtasks /Query /TN "NOOBRA Auto-Update"
# To run it now: schtasks /Run /TN "NOOBRA Auto-Update"

$ErrorActionPreference = "Stop"

$NoobraDir = Split-Path -Parent $PSScriptRoot
$UpdateBat = Join-Path $NoobraDir "update.bat"
$TaskName = "NOOBRA Auto-Update"

if (-not (Test-Path $UpdateBat)) {
    Write-Error "update.bat not found at $UpdateBat. Run this script from inside the NOOBRA folder."
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Git is not installed. Install it from https://git-scm.com/download/win and run this script again."
    exit 1
}

# A scheduled task on a ZIP extract would fail every 30 minutes in silence.
# Refuse the setup and explain how to convert the folder instead.
git -C $NoobraDir rev-parse --is-inside-work-tree 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error @"
'$NoobraDir' is not a Git clone, so update.bat can never pull anything.

Fix it once:
  1. In the PARENT folder:  git clone https://github.com/Itx-Munawar/NOOBRA.git NOOBRA-new
  2. Copy your .env into NOOBRA-new\
  3. Run setup.bat inside NOOBRA-new\
  4. Run this script again from inside NOOBRA-new\

Then use NOOBRA-new from now on (and set your shortcuts to it).
"@
    exit 1
}

# schtasks needs the command quoted because the path can contain spaces.
$TaskCommand = "`"$UpdateBat`" --silent"

Write-Host "Creating scheduled task '$TaskName'..."
Write-Host "  Folder : $NoobraDir"
Write-Host "  Runs   : every 30 minutes, while you are logged in"
Write-Host ""

# /SC MINUTE /MO 30 = every 30 minutes. /F overwrites an old task of the same name.
schtasks /Create /TN $TaskName /TR $TaskCommand /SC MINUTE /MO 30 /F
if ($LASTEXITCODE -ne 0) {
    Write-Error "Could not create the scheduled task (schtasks exit code $LASTEXITCODE). Try running PowerShell as Administrator."
    exit 1
}

# Confirm the task really exists before telling the user it is on.
schtasks /Query /TN $TaskName | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "The task was reported as created but cannot be queried. Open Task Scheduler and check '$TaskName'."
    exit 1
}

Write-Host ""
Write-Host "Done! NOOBRA will now check GitHub for updates every 30 minutes."
Write-Host "After an update, restart NOOBRA to use the new code."
Write-Host "To remove it later: schtasks /Delete /TN `"$TaskName`" /F"
