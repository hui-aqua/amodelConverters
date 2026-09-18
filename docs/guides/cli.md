# Command-line interface

[Back to README](../../README.md) · [GUI guide](gui.md) · [Replay timing](timing.md)

Run PowerShell from the repository root. The command-line workflows run inside Blender and do not require PySide6 or a separate Python installation.

```powershell
$blender = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
```

Use `launchers/cli/run_workflow.py` as the single entry point:

| Workflow | Input | Result |
|---|---|---|
| `model` | `.amodel` | Illustrative Blender physics and salmon |
| `replay-scene` | `.amodel` + results text | Complete structural replay, with optional salmon |
| `replay` | `.amodel` + results text | Geometry-only replay, for separate-stage use |
| `fish` | Open geometry-only replay `.blend` | Styled replay with a school |

## Model and Blender physics

This command uses an included example:

```powershell
& $blender --background --factory-startup --python-exit-code 1 `
  --python launchers/cli/run_workflow.py -- model examples/models/winch_cage.amodel `
  --cap-openings --pin-top --fish-count 1000 --frames 120 `
  -o output/model_scene.blend
```

For your own case, replace the `.amodel` path. If it includes attached flaps/internal sheets, select the enclosing walls and bottom with `--membrane-ids`. For the local `944ENR.amodel`, append `--membrane-ids 3 4`. The model workflow omits unselected membranes. `--cap-openings` explicitly adds invisible planar containment caps; `--pin-top` adds top-rim cloth support.

## Replay with salmon in one command

First set these paths to your matching input files. The following filenames are placeholders:

```powershell
$model = 'inputs/models/my_cage.amodel'
$results = 'inputs/results/my_case_out.txt'

& $blender --background --factory-startup --python-exit-code 1 `
  --python launchers/cli/run_workflow.py -- replay-scene $model $results `
  --wave-period 5 --frames-per-wave 40 --fps 25 `
  --add-fish --fish-count 1000 -o output/replay_salmon.blend
```

**Replace the example wave values with your AquaSim export settings.** `--frames-per-wave` means structural intervals per wave cycle. The sample interval is wave period divided by that count. The results file determines the total sample count; both replay and fish use the resulting timeline. No `--frames` is needed. See [Timing](timing.md).

Append `--membrane-ids 3 4` for the local rectangular example when adding fish. In replay, this selects containment membranes while preserving all visible source components. Planar openings are capped for containment by default; `--no-cap-openings` disables that behavior.

To create structural replay without salmon, omit `--add-fish`. No enclosing membrane selection is then needed. `replay-scene` skips preview rendering; open the saved file in Blender to render it. When the physical sample interval is already known, `--step-seconds 0.125` can be used instead of the wave options.

## Separate replay and fish stages

Useful when creating several fish variants from the same structural replay:

```powershell
& $blender --background --factory-startup --python-exit-code 1 `
  --python launchers/cli/run_workflow.py -- replay $model $results `
  --wave-period 5 --frames-per-wave 40 --fps 25 --skip-render `
  -o output/structure.blend

& $blender --background output/structure.blend --python-exit-code 1 `
  --python launchers/cli/run_workflow.py -- fish --fish-count 1000 --skip-render `
  -o output/replay_salmon.blend
```

The fish stage inherits the open replay's timing; it does not set a second FPS or wave period. Rebuild both stages when changing structural timing. For these separate stages, omitting `--skip-render` also renders a preview.

## Defaults and help

Salmon default to 0.775 m and nominal 5 kg. Model animation defaults to 120 frames at 24 fps; replay defaults to 25 fps. `--speed` is in metres per second, and `--seed` controls reproducibility. Custom fish appearance options are described in [Fish assets](fish-assets.md).

```powershell
& $blender --background --python launchers/cli/run_workflow.py -- --help
& $blender --background --python launchers/cli/run_workflow.py -- model --help
& $blender --background --python launchers/cli/run_workflow.py -- replay-scene --help
```

CLI commands replace their requested output filenames. Use different `-o` paths to keep variants. GUI builds additionally ask before replacing an existing scene. For automation, retain `--python-exit-code 1` so failures return a nonzero exit status.

Older `scripts/run_workflow.py`, `build_scene.py`, `animate_results.py`, and `style_replay.py` entry points still work. New commands should use `launchers/cli/`.
