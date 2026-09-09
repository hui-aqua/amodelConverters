# Replaceable fish models and species

Fish appearance is separated from schooling in `src/sim2blender/blender/fish/`. Both supported workflows use the same `load_fish_template()` port and `add_fish_school()` motion generator.

## Prepare a species asset

1. Import or model the fish in Blender. Join its body, fins and other visible parts into **one mesh object**; multiple material slots and UVs are supported.
2. Orient its forward direction along **+X**, with **+Z up**. Apply any desired pose and modifiers. Remove parenting, object animation and shape keys. Animated rigs are not supported by this static mesh port.
3. Name the object, for example `Salmon`. Save the asset as `assets/fish/salmon.blend`. Pack texture images into the source `.blend` so it is portable. Supply assets you have permission to use.
4. Pass the asset path, object name and species label to either workflow.

```powershell
# Append these options to the model or fish workflow command:
--fish-asset assets/fish/salmon.blend --fish-object Salmon `
--fish-species atlantic-salmon --fish-length 0.6
```

No salmon model is bundled; this is an example asset name. `--fish-object` may be omitted only when the file contains exactly one object. Non-mesh, animated, parented, modifier-dependent, empty and invalid assets are rejected with an error.

## What the importer does

The selected object is appended without executing scripts. Its transform is incorporated into its mesh, its bounding-box center is placed at the school object's origin, and its full X extent is scaled to `--fish-length` metres. The mesh and materials are shared among all fish. Existing species colors and materials are preserved by studio styling.

Clearance is the maximum vertex distance from the normalized origin plus a small margin. The school generator uses that radius for every containment check, including wider fins or unusual body shapes. Saved-scene validators use the recorded `fish_clearance_radius`; old procedural scenes retain their legacy fallback.

Without `--fish-asset`, the original procedural fish is retained for backward compatibility. Its `--fish-length` parameter scales the template (the full X extent is 1.05 times that parameter); custom assets use the requested length as their full X extent.

`--fish-species` is metadata only. It does not select a built-in species, provide biologically calibrated behavior or change swimming speed. `--speed` and `--seed` still control the existing artistic school. Changing species dimensions or mesh requires rebuilding the school, because clearance changes.

## Extension boundary

`FishTemplate` supplies a Blender mesh, conservative clearance radius, custom-material flag and source identifier. `load_fish_template()` is the appearance port; schooling consumes the template without knowing its source format.

Future formats should produce that same normalized template and preserve packed materials. Future rigged fish need a clearance envelope covering **every pose**, animation retargeting, and corresponding containment tests. Do not enable animated append-only assets without these additions.
