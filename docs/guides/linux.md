# Linux setup

Sim2Blender's GUI and Blender workflows use portable Python, Qt, and Blender
APIs. Use Blender 5.2 to match the version tested on Windows. Native Linux
Blender execution has not yet been verified in the current development session.

## Desktop GUI

Install Blender and Python 3.11 or newer with `venv` and `pip` support. Clone or
copy the repository, including `assets/` and `examples/`, then run from its root:

```sh
sh "Start Sim2Blender.sh"
```

The launcher creates `.venv-linux` and installs PySide6 on first use (internet
required). It leaves any Windows `.venv` untouched. Subsequent launches reuse
the Linux environment. To select another Python:

```sh
PYTHON=/usr/bin/python3.12 sh "Start Sim2Blender.sh"
```

Alternatively, manage your own environment:

```sh
python3 -m venv .venv-linux
. .venv-linux/bin/activate
python -m pip install -e '.[gui]'
sim2blender-gui
```

Blender is discovered via `BLENDER_PATH`, then `PATH`, standard Linux locations
(including `/snap/bin/blender`), and `blender*` folders in `/opt` or `~/.local/opt`.
For a downloaded Blender archive, extract the complete folder and point to its
executable, for example:

```sh
export BLENDER_PATH="$HOME/Applications/blender-5.2.0-linux-x64/blender"
sh "Start Sim2Blender.sh"
```

You can also select the extensionless `blender` executable in GUI Advanced
settings. It must have execute permission. Do not select the installation folder
or a `.desktop` shortcut. Flatpak is not automatically launched; use a native
Blender executable for this workflow. Snap sandbox permissions must allow access
to your project and output paths.

The GUI needs a graphical desktop and the system libraries required by Qt.
If startup reports an `xcb` plugin error, install the missing libraries using
your distribution's package manager; consult [Qt's Linux requirements](https://doc.qt.io/qt-6/linux-requirements.html).
On Ubuntu/Debian, `python3-venv` provides venv support and `libxcb-cursor0` is a
commonly required Qt dependency. Exact package requirements depend on the OS.

## Blender command line

The Blender workflows do not need PySide6 or a GUI Python environment. From the
repository root:

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python launchers/cli/run_workflow.py -- model examples/models/winch_cage.amodel \
  --cap-openings --pin-top --fish-count 10 --frames 20 \
  -o output/linux_model.blend
```

For a saved GUI job (update any Windows input/output paths in the JSON first):

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python launchers/cli/run_workflow.py -- pipeline --config output/my_scene.job.json
```

These use Blender's [standard command-line scripting interface](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html).
Use quoted paths when names contain spaces. Linux paths and asset filenames are
case-sensitive. A copied Windows virtual environment cannot be reused on Linux.

## Verify a Linux installation

After installing the project into your Linux environment, run:

```sh
python -m unittest discover -s tests/gui -p test_gui_model_job.py -v
python -m unittest discover -s tests/unit/core -v
blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender/test_environment.py
```

The Blender test checks wave surfaces, feed trajectories, fish response to
currents and JONSWAP waves, and cloth forcing. Also run the small model command
above to verify the complete scene-building path on your machine.
