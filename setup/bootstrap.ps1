# Aurora Companion - Windows bootstrap (started by Setup.bat)
# 1) finds a usable Python 3.10-3.13 (with tkinter)
# 2) if none, offers to install Python 3.11.9 from python.org for THIS USER ONLY (no admin)
# 3) opens the graphical setup wizard (setup\aurora_setup.py)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$AppRoot = Split-Path -Parent $PSScriptRoot
$PyVersion = '3.11.9'
$PyUrl = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-amd64.exe"
$PySha256 = '5ee42c4eee1e6b4464bb23722f90b45303f79442df63083f05322f1785f5fdde'

function Write-Title($t) { Write-Host ''; Write-Host "  $t" -ForegroundColor Magenta; Write-Host '' }

function Test-Python([string]$exe, [string[]]$pre) {
    try {
        $out = & $exe @pre -c "import sys, tkinter, venv, ssl; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
        $v = [version]("$out".Trim())
        if ($v -ge [version]'3.10' -and $v -lt [version]'3.14') { return $v }
    } catch { }
    return $null
}

function Find-Python {
    $cands = @()
    if ($env:AURORA_PYTHON -and (Test-Path $env:AURORA_PYTHON)) { $cands += [pscustomobject]@{ Exe = $env:AURORA_PYTHON; Pre = @() } }
    $local = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    foreach ($n in 'Python311', 'Python312', 'Python310', 'Python313') {
        $p = Join-Path $local "$n\python.exe"
        if (Test-Path $p) { $cands += [pscustomobject]@{ Exe = $p; Pre = @() } }
    }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { foreach ($v in '-3.11', '-3.12', '-3.10', '-3.13') { $cands += [pscustomobject]@{ Exe = $py.Source; Pre = @($v) } } }
    foreach ($c in (Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
        # skip the Microsoft Store placeholder (it opens the Store instead of running)
        if ($c.Source -notlike '*WindowsApps*') { $cands += [pscustomobject]@{ Exe = $c.Source; Pre = @() } }
    }
    foreach ($c in $cands) {
        $v = Test-Python $c.Exe $c.Pre
        if ($v) { return [pscustomobject]@{ Exe = $c.Exe; Pre = $c.Pre; Ver = $v } }
    }
    return $null
}

Write-Title 'Aurora Companion - Setup'
Write-Host "  App folder: $AppRoot"
if (-not [Environment]::Is64BitOperatingSystem) {
    Write-Host '  Sorry - Aurora needs 64-bit Windows.' -ForegroundColor Red
    exit 1
}

$found = Find-Python
if (-not $found) {
    Write-Host '  Python (a free programming language from python.org) is needed and was not found.'
    Write-Host "  Setup can download the official Python $PyVersion installer (approx. 26 MB download,"
    Write-Host '  approx. 110 MB installed) for your Windows user only - no administrator password needed.'
    Write-Host '  Python is third-party software owned by the Python Software Foundation (PSF License).'
    Write-Host '  Downloading it is at your own discretion; the Aurora Companion author does not own it.'
    Write-Host ''
    $ans = Read-Host '  Download and install Python now? (Y/N)'
    if ($ans -notmatch '^[Yy]') {
        Write-Host '  OK - install Python 3.11 from https://www.python.org/downloads/ and run Setup again.'
        exit 1
    }
    $tmp = Join-Path $env:TEMP "python-$PyVersion-amd64.exe"
    Write-Host '  Downloading Python...'
    Invoke-WebRequest -Uri $PyUrl -OutFile $tmp -UseBasicParsing
    $hash = (Get-FileHash $tmp -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $PySha256) {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
        Write-Host '  The download was corrupted (checksum mismatch). Please run Setup again.' -ForegroundColor Red
        exit 1
    }
    Write-Host '  Installing Python for this user (takes a minute)...'
    $p = Start-Process -FilePath $tmp -Wait -PassThru -ArgumentList @(
        '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_test=0', 'Include_doc=0',
        'Include_launcher=0', 'Include_tcltk=1', 'Include_pip=1', 'Shortcuts=0')
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    if ($p.ExitCode -ne 0) {
        Write-Host "  Python installer returned code $($p.ExitCode)." -ForegroundColor Red
    }
    $found = Find-Python
    if (-not $found) {
        Write-Host '  Python still not found. Install Python 3.11 from python.org and run Setup again.' -ForegroundColor Red
        exit 1
    }
    $env:AURORA_PY_INSTALLED = '1'
}

$exe = $found.Exe; $pre = @($found.Pre); $ver = $found.Ver
Write-Host "  Using Python $ver at $exe $pre"
Write-Host '  Opening the setup window... (keep this black window open - it shows progress details)'
& $exe @pre (Join-Path $PSScriptRoot 'aurora_setup.py') @args
exit $LASTEXITCODE
