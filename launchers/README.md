# Application entry points

| Interface | Start here | Runs |
|---|---|---|
| Windows GUI | Root `Start Sim2Blender.cmd` | `gui/start.ps1`, then `gui/app.py` |
| GUI with your own Python | `python launchers/gui/app.py` | PySide6 desktop application |
| Blender command line | `blender --background --python launchers/cli/run_workflow.py -- ...` | Shared `sim2blender.cli.blender_entry` dispatcher |

Install the GUI dependency with `python -m pip install -e ".[gui]"` when using your own Python. The Windows launcher handles its local environment automatically.

Both interfaces call `src/sim2blender/workflows/`; there is one implementation of each workflow. CLI usage is described in [the command-line guide](../docs/guides/cli.md), and desktop usage in [the GUI guide](../docs/guides/gui.md).
