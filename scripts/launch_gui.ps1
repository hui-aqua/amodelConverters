# Compatibility launcher. The canonical desktop bootstrap lives in launchers/gui.
$projectDirectory = Split-Path -Parent $PSScriptRoot
& (Join-Path $projectDirectory 'launchers/gui/start.ps1')
