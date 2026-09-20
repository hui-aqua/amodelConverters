# Sim2Blender Scripts & Standalone Tools

This directory contains standalone execution scripts, modular animation wrappers, and maintenance utilities.

## Modular Simulation Scripts (Runnable in Blender)

All optional animation and physics modules are implemented with their core logic in `src/sim2blender/blender/`, while the scripts below expose editable top-level configuration constants and can be executed directly inside Blender's **Scripting** workspace or from the command line:

| Script | Core Module | Function |
|---|---|---|
| [`blender_aquasim_replay.py`](blender_aquasim_replay.py) | `sim2blender.blender.replay` | Replaces cloth simulation with AquaSim results displacements (`out.txt`) using shape keys |
| [`blender_fish_schooling.py`](blender_fish_schooling.py) | `sim2blender.blender.fish.school` | Simulates boid salmon schooling contained within the 3D cage geometry |
| [`blender_feed_animation.py`](blender_feed_animation.py) | `sim2blender.blender.feed` | Imports spreader models (`spreader_move.obj`), animates rotor, and calculates air/water pellet trajectories |
| [`blender_fish_feeding_animation.py`](blender_fish_feeding_animation.py) | `sim2blender.blender.fish.feeding` | Simulates fish feeding behavior coupled with sinking feed pellets |
| [`blender_cinematic_camera.py`](blender_cinematic_camera.py) | `sim2blender.blender.camera` | Generates a 3-phase automated camera movement (aerial overview $\rightarrow$ spreader swoop $\rightarrow$ underwater dive) with autofocus DOF |

### Example Command-Line Usage

```bash
# Run any module directly on an existing blend file:
blender output/scene.blend --python scripts/blender_feed_animation.py
blender output/scene.blend --python scripts/blender_fish_feeding_animation.py
blender output/scene.blend --python scripts/blender_cinematic_camera.py
```

---

## Compatibility & Maintenance Scripts

| Existing path | Preferred entry point / Description |
|---|---|
| `scripts/gui.py`, `scripts/launch_gui.ps1` | `Start Sim2Blender.cmd` / `launchers/gui/app.py` |
| `scripts/run_workflow.py` | `launchers/cli/run_workflow.py` |
| `scripts/build_scene.py` | CLI `model` workflow |
| `scripts/animate_results.py` | CLI `replay` workflow |
| `scripts/style_replay.py` | CLI `fish` workflow |
| `scripts/refresh_scene.py` | Scene re-evaluation and verification utility |
| `scripts/render_previews.py` | Headless turntable and thumbnail rendering |
| `scripts/plot_project_stats.py` | Project code and statistics plotting helper |
