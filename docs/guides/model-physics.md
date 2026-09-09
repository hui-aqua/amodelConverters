# Model with Blender physics and fish

Input: one AquaSim `.amodel`. Output: a Blender scene with illustrative membrane/rope physics, rigid beam supports, materials and contained fish. This workflow does not read `out.txt`.

From the repository root:

```powershell
$blender = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
& $blender --background --factory-startup --python-exit-code 1 `
  --python scripts/run_workflow.py -- model examples/models/winch_cage.amodel `
  --cap-openings --pin-top --fish-count 1000 --frames 120 `
  -o output/fish_cage.blend
```

Play frames 1–120 at the workflow's existing 24 fps default. Use Material Preview for transparency, or F12 for the studio render.

| Option | Default / meaning |
|---|---|
| `--frames` | 120 Blender simulation frames |
| `--fish-count` | 1000; use 0 for a cage-only scene |
| `--fish-length` | 0.6 m sizing parameter; see the fish asset guide |
| `--speed` | 0.6 m/s of artistic swimming |
| `--seed` | 7, deterministic placement and motion |
| `--membrane-ids` | Select an enclosing subset of active membranes |
| `--cap-openings` | Explicitly add invisible containment caps |
| `--pin-top` | Add illustrative top-rim supports |
| `--fish-asset`, `--fish-object`, `--fish-species` | Shared custom-fish interface |
| `-o` | Output `.blend` path |

The supplied `winch_cage.amodel` requires two containment caps. `riktig_amodel_ULS.amodel` can also be used with `--cap-openings --pin-top`; its coarse/fine seam is stitched through existing source nodes. The older `ENCC100323640.amodel` requires an enclosing subset such as `--membrane-ids 4`.

The builder bakes the net first, then ropes and their attachment targets, then places fish against the evaluated enclosure. Node constraints, source sections, rope diameters, packed net materials and studio lights are retained. Beams remain stationary; attachments are coupled one way. This is illustrative physics, not an AquaSim replacement.

Rebuild after changing geometry, physics, attachments, fish dimensions or fish appearance. For shading-only changes to this cloth workflow, the legacy `scripts/refresh_scene.py` command remains available. Do not use it on a results replay.

See [fish assets](fish-assets.md), [modeling assumptions](../modeling.md), and [validation](../development.md).
