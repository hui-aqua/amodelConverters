#!/bin/sh
# Run with: sh "Start Sim2Blender.sh"
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
gui_python="$project_dir/.venv-linux/bin/python"

if [ ! -x "$gui_python" ]; then
    supports_gui_python() {
        "$1" -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1
    }
    base_python=${PYTHON:-}
    if [ -z "$base_python" ]; then
        for candidate in python3 python3.14 python3.13 python3.12 python3.11 \
            /opt/blender*/*/python/bin/python3.* \
            "$HOME"/.local/opt/blender*/*/python/bin/python3.* \
            "$HOME"/Applications/blender*/*/python/bin/python3.*; do
            if supports_gui_python "$candidate"; then
                base_python=$candidate
                break
            fi
        done
    fi
    if [ -z "$base_python" ] || ! supports_gui_python "$base_python"; then
        echo 'No usable Python 3.11+ with venv and pip support found.' >&2
        echo 'Install one, or run: PYTHON=/path/to/python3.11 sh "Start Sim2Blender.sh"' >&2
        exit 1
    fi
    printf 'Using Python: %s\n' "$base_python"
    echo 'Creating the local Linux GUI environment (first launch only)...'
    "$base_python" -m venv "$project_dir/.venv-linux"
fi

if ! "$gui_python" -c 'import PySide6.QtWidgets' >/dev/null 2>&1; then
    echo 'Installing the Qt desktop components (first launch needs internet)...'
    "$gui_python" -m pip install 'PySide6-Essentials>=6.8,<7'
fi
cd "$project_dir"
exec "$gui_python" "$project_dir/launchers/gui/app.py" "$@"
