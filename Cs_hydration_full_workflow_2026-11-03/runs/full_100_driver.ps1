param([switch]$Status,[switch]$AnalysisOnly,[switch]$DryRun,[double]$CritFreq=125.0,[int]$Workers=5,[int]$RelaxWorkers=4,[int]$Threads=1)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$driver = Join-Path $root 'scripts\cs_driver.py'
# Prefer python.exe. Windows `py` honors #!/usr/bin/env python3 and can select a
# missing Python 3.9 install (Win32 0x80070003), which aborts the whole series.
$venvPy = Join-Path $root '.venv\bin\python'
$python = if (Test-Path $venvPy) { $venvPy } elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' } elseif (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
$extra = @()
if ($Status) { $extra += '--status' }
if ($AnalysisOnly) { $extra += '--analysis-only' }
if ($DryRun) { $extra += '--dry-run' }
$extra += @('--critfreq', [string]$CritFreq, '--workers', [string]$Workers, '--relax-workers', [string]$RelaxWorkers, '--threads', [string]$Threads)
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch {}
& $python $driver @extra
exit $LASTEXITCODE
