# Feed Spreader Assets

This directory contains 3D assets for fish farm feed spreaders (rotor arms and stationary bases).

Spreader OBJ files use +Y up and -Z forward. Import converts coordinates to
Blender's +Z up (`(x, y, z)` becomes `(x, -z, y)`) and bakes this into mesh
vertices so waterline positioning and rotor animation preserve the orientation.

## Directory Structure

```text
assets/spreaders/
├── default/
│   ├── spreader_move.obj    # Rotating rotor arm
│   ├── spreader_move.mtl
│   ├── spreader_still.obj   # Stationary mounting base
│   └── spreader_still.mtl
└── wb/
    ├── WB_spreader_move.obj # Wide-beam / alternate rotating rotor arm
    ├── WB_spreader_move.mtl
    ├── WB_spreader_still.obj# Stationary base (local reference)
    └── WB_spreader_still.mtl
```

## Adding New Spreader Models

When adding new spreader models in the future:
1. Create a dedicated subfolder under `assets/spreaders/<model_name>/` (e.g. `assets/spreaders/steinsvik/` or `assets/spreaders/akva/`).
2. Provide two OBJ files (with their materials/textures):
   - **Rotor / Moving Part**: Named with `move` in the filename (e.g. `spreader_move.obj` or `<name>_move.obj`). This part will be parented to the rotating empty and driven at the configured RPM (default 30 RPM).
   - **Stationary Base**: Named with `still` in the filename (e.g. `spreader_still.obj` or `<name>_still.obj`). This part remains fixed in world space.
3. In the GUI or CLI, point `spreader_move_obj` and `spreader_still_obj` to the corresponding OBJ paths.
