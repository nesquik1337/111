param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    py -m venv .venv
}

$python = ".\.venv\Scripts\python.exe"

if (-not $SkipInstall) {
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements.txt
}

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host ".env создан из .env.example. Заполни BOT_TOKEN и запусти скрипт снова."
    exit 0
}

& $python bot.py
