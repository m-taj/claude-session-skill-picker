# Installer for claude-session-skill-picker on Windows.
# Run from PowerShell:   powershell -ExecutionPolicy Bypass -File .\install.ps1

$ErrorActionPreference = 'Stop'

$HookDir   = Join-Path $env:USERPROFILE '.claude\hooks'
$Settings  = Join-Path $env:USERPROFILE '.claude\settings.json'
$ScriptDir = Split-Path -Parent $PSCommandPath

Write-Host 'Installing claude-session-skill-picker...'

# --- 1. Find a Python interpreter --------------------------------------------
function Find-Python {
    foreach ($cmd in @('py -3', 'python', 'python3')) {
        $parts = $cmd -split ' '
        $exe   = $parts[0]
        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            try {
                $out = & $exe $parts[1..($parts.Length-1)] --version 2>&1
                if ($LASTEXITCODE -eq 0 -and $out -match 'Python 3') {
                    return $cmd
                }
            } catch {}
        }
    }
    return $null
}

$PyCmd = Find-Python
if (-not $PyCmd) {
    Write-Host '  X Python 3 not found. Install from https://www.python.org/downloads/ and rerun.'
    exit 1
}
Write-Host "  + Python 3 found (invocation: $PyCmd)"

# --- 2. Copy scripts ---------------------------------------------------------
New-Item -ItemType Directory -Force -Path $HookDir | Out-Null
foreach ($f in @('skills-launch.py', 'skills-picker.py', 'skills-inject.py')) {
    $src = Join-Path $ScriptDir $f
    $dst = Join-Path $HookDir   $f
    Copy-Item -Force -Path $src -Destination $dst
    Write-Host "  + Installed $dst"
}

# --- 3. Patch settings.json --------------------------------------------------
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Settings) | Out-Null
if (-not (Test-Path $Settings)) {
    '{}' | Set-Content -Path $Settings -Encoding UTF8
}

$json = Get-Content $Settings -Raw | ConvertFrom-Json

if (-not $json.PSObject.Properties['hooks']) {
    $json | Add-Member -NotePropertyName 'hooks' -NotePropertyValue ([pscustomobject]@{})
}

$launchHookCmd = "$PyCmd `"$HookDir\skills-launch.py`""
$injectHookCmd = "$PyCmd `"$HookDir\skills-inject.py`""

$launchEntry = [pscustomobject]@{
    matcher = ''
    hooks   = @(
        [pscustomobject]@{
            type    = 'command'
            command = $launchHookCmd
            async   = $true
        }
    )
}
$injectEntry = [pscustomobject]@{
    matcher = ''
    hooks   = @(
        [pscustomobject]@{
            type    = 'command'
            command = $injectHookCmd
            timeout = 5
        }
    )
}

function Filter-Out($list, $needle) {
    if (-not $list) { return @() }
    return @($list | Where-Object {
        $keep = $true
        foreach ($h in $_.hooks) {
            if ($h.command -match [regex]::Escape($needle)) { $keep = $false }
        }
        $keep
    })
}

if (-not $json.hooks.PSObject.Properties['SessionStart'])     { $json.hooks | Add-Member SessionStart @() }
if (-not $json.hooks.PSObject.Properties['UserPromptSubmit']) { $json.hooks | Add-Member UserPromptSubmit @() }

$json.hooks.SessionStart     = @(Filter-Out $json.hooks.SessionStart     'skills-launch.py')  + $launchEntry
$json.hooks.UserPromptSubmit = @(Filter-Out $json.hooks.UserPromptSubmit 'skills-inject.py')  + $injectEntry

$json | ConvertTo-Json -Depth 20 | Set-Content -Path $Settings -Encoding UTF8
Write-Host "  + Patched $Settings"

Write-Host ''
Write-Host 'Done. Start a new Claude Code session to see the skill picker.'
Write-Host 'Disable temporarily with:  $env:CLAUDE_SKILLS_PICKER = "off"'
