# Uninstaller for claude-session-skill-picker on Windows. Mirrors install.ps1 in reverse.
# Run from PowerShell:   powershell -ExecutionPolicy Bypass -File .\uninstall.ps1

$ErrorActionPreference = 'Stop'

$HookDir  = Join-Path $env:USERPROFILE '.claude\hooks'
$Settings = Join-Path $env:USERPROFILE '.claude\settings.json'
$CacheDir = Join-Path $env:USERPROFILE '.claude\cache'

Write-Host 'Uninstalling claude-session-skill-picker...'

# --- 1. Disconnect any connected agents first --------------------------------
# Each adapter's own uninstall() strips only its own hook/plugin entries —
# never touches unrelated hooks/config the user has for that agent.
$adaptersDir = Join-Path $HookDir 'adapters'
if (Test-Path $adaptersDir) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
    if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
    if ($py) {
        Get-ChildItem -Path $adaptersDir -Filter '*.py' -ErrorAction SilentlyContinue | ForEach-Object {
            try { & $py.Source $_.FullName uninstall } catch {}
        }
    }
}

# --- 2. Remove installed scripts + assets ------------------------------------
foreach ($f in @('skills-launch.py', 'skills-picker.py', 'skills-inject.py', 'skills-settings.py', 'skills-suggest.py', 'skills-update.py', 'licensing.py', 'VERSION', 'CHECKSUMS.txt', 'skills-picker-overrides.json')) {
    $p = Join-Path $HookDir $f
    if (Test-Path $p) {
        Remove-Item -Force $p
        Write-Host "  + Removed $p"
    }
}
$imgDir = Join-Path $HookDir 'images'
if (Test-Path $imgDir) {
    Remove-Item -Recurse -Force $imgDir
    Write-Host "  + Removed $imgDir"
}
if (Test-Path $adaptersDir) {
    Remove-Item -Recurse -Force $adaptersDir
    Write-Host "  + Removed $adaptersDir"
}
$desktopDir = [Environment]::GetFolderPath('Desktop')
if ($desktopDir) {
    $desktopShortcut = Join-Path $desktopDir 'Skill Picker Settings.lnk'
    if (Test-Path $desktopShortcut) {
        Remove-Item -Force $desktopShortcut
        Write-Host "  + Removed Desktop shortcut"
    }
}

# --- 3. Clear cache/state files -----------------------------------------------
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-catalog.json')
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-remembered-picks.json')
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-repo-sources.json')
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-connected-agents.json')
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-picker-prefs.json')
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-usage-history.json')
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-suggestions-cache.json')
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-update-cache.json')
Remove-Item -ErrorAction SilentlyContinue -Recurse -Force (Join-Path $CacheDir 'skill-repos')
Remove-Item -ErrorAction SilentlyContinue -Recurse -Force (Join-Path $CacheDir 'self-update')
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-spawned-*.txt')
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-pending-*.txt')
Remove-Item -ErrorAction SilentlyContinue -Force (Join-Path $CacheDir 'skills-picker-*.log')
Write-Host "  + Cleared cache files"

# --- 4. Strip the hook entries from settings.json ----------------------------
if (Test-Path $Settings) {
    $json = Get-Content $Settings -Raw | ConvertFrom-Json
    if ($json.PSObject.Properties['hooks']) {
        if ($json.hooks.PSObject.Properties['SessionStart']) {
            $json.hooks.SessionStart = @($json.hooks.SessionStart | Where-Object {
                $keep = $true
                foreach ($h in $_.hooks) {
                    if ($h.command -match 'skills-launch\.py') { $keep = $false }
                }
                $keep
            })
        }
        if ($json.hooks.PSObject.Properties['UserPromptSubmit']) {
            $json.hooks.UserPromptSubmit = @($json.hooks.UserPromptSubmit | Where-Object {
                $keep = $true
                foreach ($h in $_.hooks) {
                    if ($h.command -match 'skills-inject\.py') { $keep = $false }
                }
                $keep
            })
        }
        $json | ConvertTo-Json -Depth 20 | Set-Content -Path $Settings -Encoding UTF8
        Write-Host "  + Removed hook entries from $Settings"
    }
} else {
    Write-Host "  ~ No settings.json found, nothing to patch."
}

Write-Host ''
Write-Host 'Done. Skill picker removed. Restart Claude Code to complete.'

# Remove self last.
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $HookDir 'uninstall.ps1')
