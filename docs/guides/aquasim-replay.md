# AquaSim replay with synchronized fish

This workflow reads active connectivity from `.amodel` and absolute node positions from `out.txt`. AquaSim drives structural motion; Blender generates the fish and rendering.

## Build geometry, then add fish

The large `examples/models/out.txt` export is a local input excluded from Git. Supply the matching AquaSim export before running these commands, or substitute an explicit local results path. Automated small-fixture tests generate their own data.

```powershell
$blender = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
& $blender --background --factory-startup --python-exit-code 1 `
  --python scripts/run_workflow.py -- replay `
  examples/models/ENC172233860Winch_nearSurface.amodel examples/models/out.txt `
  --step-seconds 0.125 --fps 25 -o output/aquasim_replay.blend

& $blender --background output/aquasim_replay.blend --python-exit-code 1 `
  --python scripts/run_workflow.py -- fish --fish-count 1000 `
  -o output/aquasim_fish.blend
```

The first stage creates replay geometry, a `.json` mapping report and a `.png` preview. The second creates the shaded fish scene, a `.fish.json` report and a rendered preview. Files with the same output names are replaced on rerun. Use another `-o` to keep variants.

The fish stage accepts `--fish-count`, `--fish-length`, `--speed`, `--seed`, `--fish-asset`, `--fish-object`, `--fish-species`, `--samples` (Cycles samples; default 64) and `--skip-render`. Start each variant from the geometry-only replay. The full school can take several minutes to generate and verify.

## One physical clock

| Quantity | Supplied case |
|---|---|
| Structural interval | 2.5/20 = 0.125 s |
| Video rate | 25 fps |
| Fish update interval | 0.04 s |
| Structural samples / output frames | 406 / 1267 |
| First-to-last source time | 50.625 s |

Sample index `i`, starting at zero, is keyed at `frame = 1 + i * 0.125 * 25`. Fractional frame keys (1, 4.125, 7.25, ...) preserve the exact timing. The last source sample is at frame 1266.625. Frame 1267 samples its held final geometry at time 50.64 s. Encoding all 1267 frames at 25 fps gives a 50.68 s video.

Fish swim at their requested speed in metres per second relative to the cage-following motion. They are checked against interpolated structural positions at every integer video frame. The camera and lights follow the same timeline. Fish may relocate when deformation makes a position unsafe; subframe containment is not certified.

Rebuild **both stages** when changing fps or structural interval. Setting an existing 25 fps scene to 50 fps only doubles playback speed. To keep the same physical time at 50 fps, regenerate with `--fps 50 --step-seconds 0.125` and regenerate fish.

`source_times` preserves dimensionless export labels; `source_frames`, `structural_step_seconds` and `duration_seconds` record the explicit time mapping. Samples are treated as uniformly spaced by `--step-seconds` regardless of export labels.

## Mapping and geometry limits

The result table must have the header `Time [-] VID [-] X Y Z`. VIDs are solver indices, not AModel node IDs. The importer uniquely matches initial coordinates at three-decimal precision; it rejects ambiguous/missing matches, nonfinite values, duplicate VIDs, decreasing times and inconsistent node sets.

The supplied pair maps all 5,100 active model nodes; nine additional result nodes have no active geometry. A result file beginning after deformation needs a separate explicit mapping mechanism, not currently implemented.

The geometry-only replay displays finite-element edges and structural centerline tubes, with minimum visible radius/strand thickness. The styled replay adds source-sized net strands, packed open-mesh shading, HDPE supports and Cycles lighting. Section rotations are not exported. Two invisible caps close this model's openings for fish containment only. No Blender cloth or rigid-body solver changes the AquaSim motion.

## Verify a saved scene

```powershell
& $blender --background output/aquasim_fish.blend --python-exit-code 1 `
  --python tests/validation/verify_results_blend.py
```

The validator checks source topology and mapping, every exact structural key and every video frame, the hidden enclosure, fish clearance, materials, lights and camera framing. It writes `.validation.json` and `_last.png` beside the scene without saving scene changes. Input files must still exist at their recorded paths for validation; playback needs only the packed `.blend`.

See [fish assets](fish-assets.md) and [architecture](../architecture.md).
