# Beam and rope shading

## HDPE beam shading preprocessing

Imported circular beam meshes receive angle-based normal correction when visualization is applied. Objects remain separate; coordinates, connectivity, dimensions, names, source attributes and modifiers are preserved. Cylindrical walls are smooth, while cap rims above 30 degrees remain sharp and caps stay flat. Existing sharp edges are respected.

For an existing imported scene, run in Blender with the project's `src` on `sys.path`:

```python
from sim2blender.blender.beam_shading import preprocess_hdpe_beams
report = preprocess_hdpe_beams()  # Current scene, or pass collection.objects
```

Identification uses `component_type == "beam"` and `source_geometry_json.kind == "tube"`, not object names. This selects the circular beams used as HDPE in this project's visualization; it does not infer polymer composition from geometry. Untagged/noncircular objects, custom-normal meshes, linked data, edit-mode meshes and meshes shared with unselected/ineligible objects are skipped. The report includes skip reasons. The function only changes face smoothing and edge sharpness; it does not change materials or add modifiers. It uses direct mesh access and processes shared data once.

A rendered seven-segment comparison showed continuous highlights after correction. Weighted Normal with Keep Sharp produced identical corner normals on the regular tube fixture (maximum delta 0), so it is not added. Reproduce the comparison (top: original, middle: corrected, bottom: corrected plus Weighted Normal):

```powershell
& $blender --background --factory-startup --python-exit-code 1 `
  --python tests/blender/test_beam_shading.py -- --render-comparison
```

Artifacts are written to `output/hdpe_shading_comparison.png` and `.blend`. The HDPE visualization uses black, nonmetallic material, roughness 0.5 and IOR 1.5 for soft reflections. Normal correction cannot remove actual source gaps, axis changes, or mismatched segment cross sections.

## Rope shading and restrained lighting

`preprocess_rope_segments()` in `sim2blender.blender.rope_shading` automatically handles tagged AquaSim truss ropes during visualization. Static segment meshes receive radial side corner normals, suppressing lighting restarts from independent helical sweeps while retaining flat caps, original names, coordinates and connectivity. This deliberately softens the visual strand relief; the lobed silhouette is unchanged. Authored custom normals, unsupported cap layouts and shape-key meshes are skipped. Existing cloth-generated rope surfaces receive an idempotent smooth-wall/flat-cap node chain after simulation, without adding modifiers or changing the cloth cache.

To update shading and lights in an existing model scene without touching HDPE geometry, smoothing or materials:

```python
import bpy
from sim2blender.blender.rope_shading import preprocess_rope_segments
from sim2blender.blender.shading import studio
preprocess_rope_segments(bpy.context.scene.objects)
studio(bpy.context.scene)  # Requires the imported scene's Membrane cage
```

The studio now uses 25% of the previous key/fill power and 20% of the previous rim power, exposure 0 instead of +1, and World strength 0.2 instead of 0.45. Light sizes stay broad, the fill is slightly cool, and the World remains dark blue. HDPE remains black with its existing material settings. These are absolute settings, so repeated runs do not keep dimming the lights.

