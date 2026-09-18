$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$environmentDirectory = Join-Path $projectDirectory '.venv'
$guiPython = Join-Path $environmentDirectory 'Scripts/python.exe'

try {
    if (-not (Test-Path -LiteralPath $guiPython)) {
        $candidates = @()
        $pythonRoot = Join-Path $env:LOCALAPPDATA 'Programs/Python'
        if (Test-Path -LiteralPath $pythonRoot) {
            $candidates += Get-ChildItem -Path "$pythonRoot/Python*/python.exe" -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | Select-Object -ExpandProperty FullName
        }
        $blenderRoot = Join-Path $env:ProgramFiles 'Blender Foundation'
        if (Test-Path -LiteralPath $blenderRoot) {
            $candidates += Get-ChildItem -Path "$blenderRoot/Blender */*/python/bin/python.exe" -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | Select-Object -ExpandProperty FullName
        }
        $basePython = $null
        foreach ($candidate in $candidates) {
            & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
            if ($LASTEXITCODE -eq 0) { $basePython = $candidate; break }
        }
        if (-not $basePython) { throw 'Install Python 3.11+ from python.org or Blender 5.2, then launch again.' }
        Write-Host 'Creating the local Sim2Blender GUI environment (first launch only)...'
        & $basePython -m venv $environmentDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
    }
    & $guiPython -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PySide6') else 1)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing the Qt desktop components (first launch needs internet)...'
        & $guiPython -m pip install 'PySide6-Essentials>=6.8,<7'
        if ($LASTEXITCODE -ne 0) { throw 'Qt installation failed. Check your internet connection and launch again.' }
    }
    $guiScript = Join-Path $PSScriptRoot 'app.py'
    # Blender bundles python.exe but not pythonw.exe; the venv's pythonw
    # redirector therefore cannot be used reliably. Hide only the console.
    Start-Process -FilePath $guiPython -ArgumentList @('"' + $guiScript + '"') -WorkingDirectory $projectDirectory -WindowStyle Hidden
} catch {
    Write-Host "Sim2Blender could not start: $_" -ForegroundColor Red
    exit 1
}
