# Installer for claude-session-skill-picker on Windows.
# Run from PowerShell:   powershell -ExecutionPolicy Bypass -File .\install.ps1

$ErrorActionPreference = 'Stop'

$HookDir   = Join-Path $env:USERPROFILE '.claude\hooks'
$Settings  = Join-Path $env:USERPROFILE '.claude\settings.json'
$ScriptDir = Split-Path -Parent $PSCommandPath

Write-Host 'Installing claude-session-skill-picker...'

# --- 1. Find a Python interpreter --------------------------------------------
function Find-Python {
    # Prefer 'py' launcher (absolute, always at C:\Windows\py.exe). Fall back to absolute path
    # of python.exe / python3.exe. Hooks fired by the Claude Code desktop app inherit only
    # the system PATH, not the user's interactive shell PATH, so absolute paths are required.
    $candidates = @(
        @{ Cmd = 'py';      Args = @('-3') },
        @{ Cmd = 'python';  Args = @()     },
        @{ Cmd = 'python3'; Args = @()     }
    )
    foreach ($c in $candidates) {
        $found = Get-Command $c.Cmd -ErrorAction SilentlyContinue
        if (-not $found) { continue }
        $argsAll = @($c.Args) + @('--version')
        try {
            $out = & $found.Source @argsAll 2>&1
            if ($LASTEXITCODE -eq 0 -and $out -match 'Python 3') {
                $invocation = if ($c.Args.Count -gt 0) {
                    "`"$($found.Source)`" $($c.Args -join ' ')"
                } else {
                    "`"$($found.Source)`""
                }
                return $invocation
            }
        } catch {}
    }
    return $null
}

$PyCmd = Find-Python
if (-not $PyCmd) {
    Write-Host '  X Python 3 not found. Install from https://www.python.org/downloads/ and rerun.'
    exit 1
}
Write-Host "  + Python 3 found (invocation: $PyCmd)"

# --- 2. Copy scripts + overrides ---------------------------------------------
New-Item -ItemType Directory -Force -Path $HookDir | Out-Null
foreach ($f in @('skills-launch.py', 'skills-picker.py', 'skills-inject.py', 'skills-settings.py')) {
    $src = Join-Path $ScriptDir $f
    $dst = Join-Path $HookDir   $f
    Copy-Item -Force -Path $src -Destination $dst
    Write-Host "  + Installed $dst"
}

# Overrides file: do NOT overwrite if the user has already customized it.
$ovrSrc = Join-Path $ScriptDir 'skills-picker-overrides.json'
$ovrDst = Join-Path $HookDir   'skills-picker-overrides.json'
if (Test-Path $ovrDst) {
    Write-Host "  ~ Kept existing $ovrDst (delete it to reinstall the default)"
} else {
    Copy-Item -Force -Path $ovrSrc -Destination $ovrDst
    Write-Host "  + Installed $ovrDst"
}

# Logo assets — the picker loads this GIF relative to its own installed path.
$imgDstDir = Join-Path $HookDir 'images'
New-Item -ItemType Directory -Force -Path $imgDstDir | Out-Null
Copy-Item -Force -Path (Join-Path $ScriptDir 'images\skillpicker-logo.gif') -Destination (Join-Path $imgDstDir 'skillpicker-logo.gif')
Write-Host "  + Installed $(Join-Path $imgDstDir 'skillpicker-logo.gif')"

# Uninstaller — copied alongside so the picker's Settings > Uninstall button
# works even if the cloned repo is later deleted.
Copy-Item -Force -Path (Join-Path $ScriptDir 'uninstall.ps1') -Destination (Join-Path $HookDir 'uninstall.ps1')
Write-Host "  + Installed $(Join-Path $HookDir 'uninstall.ps1')"

# Per-agent adapters (Codex, OpenCode, ...) — copied alongside so the
# picker's Settings > Connected Agents section can install/uninstall them
# even if the cloned repo is later deleted.
$adaptersDstDir = Join-Path $HookDir 'adapters'
New-Item -ItemType Directory -Force -Path $adaptersDstDir | Out-Null
Copy-Item -Force -Path (Join-Path $ScriptDir 'adapters\*.py') -Destination $adaptersDstDir -ErrorAction SilentlyContinue
Copy-Item -Force -Path (Join-Path $ScriptDir 'adapters\*.js') -Destination $adaptersDstDir -ErrorAction SilentlyContinue
Write-Host "  + Installed $adaptersDstDir"

# pywebview — optional. The picker renders as HTML/CSS in a native webview when
# available and falls back automatically to the plain tkinter dialog if this
# isn't installed, so a failure here must never fail the whole install.
try {
    Invoke-Expression "$PyCmd -m pip install --quiet pywebview" | Out-Null
    Write-Host "  + Installed pywebview (richer picker UI)"
} catch {
    Write-Host "  ~ pywebview not installed - picker will use the native tkinter dialog instead"
}

# WebView2 runtime — the native component pywebview needs on Windows (pip can't
# install this, it's not a Python package). Most modern Windows already has it
# bundled with Edge; this is a no-op there. Same best-effort rule: never fail
# the whole install over it, the tkinter fallback covers this machine either way.
function Test-WebView2Installed {
    $paths = @(
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        'HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    )
    foreach ($p in $paths) {
        try {
            $v = (Get-ItemProperty -Path $p -Name 'pv' -ErrorAction SilentlyContinue).pv
            if ($v -and $v -ne '0.0.0.0') { return $true }
        } catch {}
    }
    return $false
}

if (Test-WebView2Installed) {
    Write-Host "  + WebView2 runtime already present"
} else {
    try {
        $bootstrapper = Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'
        Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $bootstrapper -UseBasicParsing
        Start-Process -FilePath $bootstrapper -ArgumentList '/silent', '/install' -Wait
        Remove-Item -Force -ErrorAction SilentlyContinue $bootstrapper
        if (Test-WebView2Installed) {
            Write-Host "  + Installed WebView2 runtime (silent)"
        } else {
            Write-Host "  ~ WebView2 install did not complete - picker will use the native tkinter dialog instead"
        }
    } catch {
        Write-Host "  ~ Could not install WebView2 runtime - picker will use the native tkinter dialog instead"
    }
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

Write-Host "  + Launch hook command: $launchHookCmd"
Write-Host "  + Inject hook command: $injectHookCmd"

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
