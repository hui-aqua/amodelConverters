# Development and validation

## Layout and entry points

`src/sim2blender` is an installable Python package. `amodel.py` and `geometry.py` contain shared parsing and section interpretation. `obj.py`, `vtp.py` and `plot.py` are CLI modules. Blender imports stay inside the `blender/` package or inside Blender-only functions, so ordinary exports and unit tests do not require `bpy`.

`blender/build.py` assembles and bakes a scene. `geometry.py` creates beam sections and round net strands; `ropes.py` simulates rope centerlines and attachment targets; `shading.py` creates packed textures, materials and lights. Blender entry scripts add `src/` to their import path, so Blender needs no editable install.

| Previous entry | Current entry |
|---|---|
| `amodel2blender.py` | `scripts/build_scene.py` |
| `amodel2obj.py` | `python -m sim2blender.obj` |
| `amodel2vtp.py` | `python -m sim2blender.vtp` |
| Two `amodel2matplot_*` scripts | `python -m sim2blender.plot` with optional `--nodes-only` |
| `amodelExamples/` | `examples/models/` |
| `BlenderFile/` | `examples/reference/` |
| `convertOutput/` | `output/` |

The long WINCH filename became `winch_cage.amodel`; source XML contents were not edited. Obsolete wrapper scripts, temporary probes, bytecode, local test dependencies and redundant generated exports are not part of the cleaned project.

## Tests

From the repository root, run the ordinary Python tests:

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
```

Then run Blender integration tests:

```powershell
$blender = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
& $blender --background --factory-startup --python-exit-code 1 --python tests/blender/test_blender.py
& $blender --background --factory-startup --python-exit-code 1 --python tests/blender/test_geometry.py
& $blender --background --factory-startup --python-exit-code 1 --python tests/blender/test_rope_dynamics.py
```

These 19 tests cover activity flags, malformed data, XYZ/export consistency, net texture transparency/coverage, concave containment, fixed/partial-axis constraints, physical section dimensions, rope sag, moving attachments and post-cloth rope diameter.

After building the WINCH trial, verify the saved artifact:

```powershell
& $blender --background output/fish_cage.blend --python-exit-code 1 --python tests/validation/verify_geometry_blend.py
& $blender --background output/fish_cage.blend --python-exit-code 1 --python tests/validation/verify_rope_blend.py
& $blender --background output/fish_cage.blend --python-exit-code 1 --python tests/validation/verify_saved_blend.py
& $blender --background output/fish_cage.blend --python-exit-code 1 --python tests/validation/verify_visualization.py
```

The geometry/rope checks are tailored to the supplied 1,000-fish WINCH trial. `verify_saved_blend.py` also renders an overview. They read the `.blend` without saving changes and write reports into `output/`.

| Report | Checks |
|---|---|
| `fish_cage.geometry.json` | Source section data, dimensions and inference warnings |
| `geometry_validation.json` | Beam mesh dimensions and rope rest-centerline dimensions |
| `rope_validation.json` | Rope caches, rigid supports, shared nodes and deformation |
| `validation.json` | Fish containment, fixed nodes and membrane bake |

## Regenerate documentation assets

```powershell
& $blender --background output/fish_cage.blend --python-exit-code 1 --python scripts/render_previews.py
python -m pip install -e '.[plots]'
python scripts/plot_project_stats.py
```

The render script writes the overview and net close-up in `docs/assets/`; it does not modify the saved scene. The chart script reads component counts and diameters directly from `examples/models/winch_cage.amodel`.

## Working on simulation changes

Use a separate `--output` for short trials. The scene builder validates fish before saving. Do not reuse downstream shape-key targets or fish animation after changing upstream cloth, geometry or attachment topology. Rebuild the full dependency chain.

For material-only changes, use `scripts/refresh_scene.py` on an existing generated scene. It updates materials, metric UVs, lights and preview settings, verifies that cloth caches remain baked, and saves the opened file.
