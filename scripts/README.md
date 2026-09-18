# Compatibility and maintenance scripts

New users should start with `Start Sim2Blender.cmd` or `launchers/cli/run_workflow.py`.

These older entry points remain supported:

| Existing path | Preferred entry point |
|---|---|
| `scripts/gui.py`, `scripts/launch_gui.ps1` | `Start Sim2Blender.cmd` / `launchers/gui/` |
| `scripts/run_workflow.py` | `launchers/cli/run_workflow.py` |
| `scripts/build_scene.py` | CLI `model` workflow |
| `scripts/animate_results.py` | CLI `replay` workflow |
| `scripts/style_replay.py` | CLI `fish` workflow |

`refresh_scene.py`, `render_previews.py`, and the plotting helpers are maintenance utilities. They are not required for ordinary GUI or CLI scene creation. Review their output/scene effects before running them on existing scenes.
