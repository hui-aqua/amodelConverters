#!/bin/sh
# Run with: sh "Start Sim2Blender.sh"
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
gui_python="$project_dir/.venv-linux/bin/python"

if [ ! -x "$gui_python" ]; then
    base_python=${PYTHON:-python3}
    if ! "$base_python" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
        echo 'Install Python 3.11+ (including venv support), or set PYTHON to its executable.' >&2
        exit 1
    fi
    echo 'Creating the local Linux GUI environment (first launch only)...'
    "$base_python" -m venv "$project_dir/.venv-linux"
fi

if ! "$gui_python" -c 'import PySide6.QtWidgets' >/dev/null 2>&1; then
    echo 'Installing the Qt desktop components (first launch needs internet)...'
    "$gui_python" -m pip install 'PySide6-Essentials>=6.8,<7'
fi
cd "$project_dir"
exec "$gui_python" "$project_dir/launchers/gui/app.py" "$@"
