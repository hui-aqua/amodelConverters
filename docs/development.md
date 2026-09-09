# Development and validation

## Working structure

See [architecture](architecture.md) for module responsibilities and extension conventions. Blender entry points insert `src/` into their import path; readers and exporters also work as an installable Python package.

```powershell
python -m pip install -e .
python -m sim2blender.exporters.obj examples/models/winch_cage.amodel
python -m sim2blender.exporters.vtp examples/models/winch_cage.amodel
```

For optional plots, install `.[plots]` and use `python -m sim2blender.exporters.plot`. The `amodel-obj`, `amodel-vtp` and `amodel-plot` console commands remain available.

## Tests

Run from the repository root:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -p 'test_*.py' -v

$blender = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
& $blender --background --factory-startup --python-exit-code 1 --python tests/blender/test_blender.py
& $blender --background --factory-startup --python-exit-code 1 --python tests/blender/test_geometry.py
& $blender --background --factory-startup --python-exit-code 1 --python tests/blender/test_rope_dynamics.py
& $blender --background --factory-startup --python-exit-code 1 --python tests/blender/test_fish_assets.py
& $blender --background --factory-startup --python-exit-code 1 --python tests/blender/test_workflows.py
```

If the Windows Python app alias fails, substitute Blender's bundled interpreter:
`& 'C:/Program Files/Blender Foundation/Blender 5.2/5.2/python/bin/python.exe' -m unittest discover -s tests -p 'test_*.py' -v`.

Python tests cover source validation, exports, timing and legacy imports. Blender tests cover enclosure geometry, constraints, cloth/rope behavior, source dimensions, shared-node attachment, fish speed, custom-asset sizing/materials/clearance, and both complete workflows on a small fixture. Integration fixtures are temporary; generated user scenes are not overwritten.

The restructuring and static fish-asset port passed **37 tests** (14 Python, 9 enclosure/school, 6 geometry, 4 rope and 4 fish-asset tests), plus the end-to-end workflow script. The latter builds both workflow variants with a custom fish asset, reopens the saved replay, checks fractional timing and verifies 24 fish/frame containment cases.

## Verify saved artifacts

```powershell
& $blender --background output/aquasim_fish.blend --python-exit-code 1 `
  --python tests/validation/verify_results_blend.py
```

The replay validator reopens source files and checks original connectivity, solver-ID mapping, physical timing, source-key and video-frame positions, hidden enclosure positions, fish clearance, packed net textures, studio lighting and camera framing. Display modifiers are disabled only during coordinate checks and restored for a final-frame preview. It writes `.validation.json` and `_last.png`; it does not save scene edits.

For the original 1,000-fish WINCH cloth example, `verify_geometry_blend.py`, `verify_rope_blend.py`, `verify_saved_blend.py` and `verify_visualization.py` remain under `tests/validation/`. Those checks are tailored to that example; they do not validate arbitrary input models.

## Migration map

| Previous implementation path | Canonical implementation |
|---|---|
| `sim2blender.amodel` | `sim2blender.io.aquasim.model` |
| `sim2blender.geometry` | `sim2blender.io.aquasim.sections` |
| `sim2blender.results` | `sim2blender.io.aquasim.results`; shared timing in `core.timeline` |
| `sim2blender.obj`, `vtp`, `plot` | `sim2blender.exporters.*` |
| `sim2blender.blender.build` | `workflows.model_physics`, `blender.scene`, `blender.enclosure`, `blender.fish.school` |
| Implementation in `scripts/animate_results.py` | `workflows.replay_geometry` |
| Implementation in `scripts/style_replay.py` | `workflows.replay_fish` |

Old imports and script entry points are compatibility facades. New commands use `scripts/run_workflow.py -- model`, `-- replay`, or `-- fish`. `replay` and `fish` are the two stages of the second user workflow, not two independent simulation backends.

Input examples retain their current filenames and paths because saved scenes record source paths. Existing `.blend` animations do not need rebuilding merely because Python modules moved. Changing fish geometry, physics or timing does require rebuilding the dependent animation. Keep user-edited scenes and create new `-o` outputs for trials.

## Maintenance utilities

`scripts/refresh_scene.py` refreshes materials on the original cloth scene. `render_previews.py` and `plot_project_stats.py` regenerate the original documentation images/plots. Their entry points remain stable. New fish assets belong in `assets/fish/`; large future datasets should use explicit user-managed input paths and generated caches under `output/`.
