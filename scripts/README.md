# Sim2Blender Scripts & Standalone Tools

This directory contains standalone execution scripts, modular animation wrappers, and maintenance utilities organized into logical categories.

```
scripts/
├── blender/         # Direct Blender scripting workspace & headless automation scripts (9 modular tools)
├── maintenance/     # Developer utilities (preview rendering, scene refresh, project stats)
└── run_workflow.py  # CLI unified workflow runner (calls launchers/cli/run_workflow.py)
```

> **Note on GUI Launcher**: To launch the GUI application, run `launchers/gui/start.ps1` or `python launchers/gui/app.py` (or double-click `Start Sim2Blender.cmd` in the repository root).

---

## 1. Modular Blender Scripts (`scripts/blender/`)

All optional animation and physics modules are implemented with their core logic in `src/sim2blender/blender/`, while the scripts in `scripts/blender/` expose editable top-level configuration constants and can be executed directly inside Blender's **Scripting** workspace or headlessly from the command line:

| Script | Core Module | Function |
|---|---|---|
| [`blender_aquasim_replay.py`](blender/blender_aquasim_replay.py) | `sim2blender.blender.replay` | Replaces cloth simulation with AquaSim results displacements (`out.txt`) using shape keys |
| [`blender_fish_schooling.py`](blender/blender_fish_schooling.py) | `sim2blender.blender.fish.school` | Simulates boid salmon schooling contained within the 3D cage geometry |
| [`blender_fish_tail_preview.py`](blender/blender_fish_tail_preview.py) | `sim2blender.blender.fish.tail` | Generates a standalone preview and animation testing the fish tail oscillating rig |
| [`blender_feed_animation.py`](blender/blender_feed_animation.py) | `sim2blender.blender.feed` | Imports spreader models (`spreader_move.obj`), animates rotor, and calculates air/water pellet trajectories |
| [`blender_spreader_waterline.py`](blender/blender_spreader_waterline.py) | `sim2blender.blender.spreader_waterline` | Interactive 3D visualization and calibration of the feed spreader water line lift and waterline intersection |
| [`blender_fish_feeding_animation.py`](blender/blender_fish_feeding_animation.py) | `sim2blender.blender.fish.feeding` | Simulates fish feeding behavior coupled with sinking feed pellets |
| [`blender_feeding_camera.py`](blender/blender_feeding_camera.py) | `sim2blender.blender.feeding_camera` | Sets up automated camera tracking for feeding operations |
| [`blender_cinematic_camera.py`](blender/blender_cinematic_camera.py) | `sim2blender.blender.camera` | Generates a 3-phase automated camera movement (aerial overview $\rightarrow$ spreader swoop $\rightarrow$ underwater dive) with autofocus DOF |
| [`blender_model_preview.py`](blender/blender_model_preview.py) | `sim2blender.blender.preview` | Quickly visualizes `.amodel` meshes and geometry directly in Blender |

### Example Command-Line Usage

```bash
# Run any module directly on an existing blend file:
blender output/scene.blend --python scripts/blender/blender_feed_animation.py
blender output/scene.blend --python scripts/blender/blender_fish_feeding_animation.py
blender output/scene.blend --python scripts/blender/blender_cinematic_camera.py
```

---

## 2. Maintenance & Developer Utilities (`scripts/maintenance/`)

| Script | Description |
|---|---|
| [`refresh_scene.py`](maintenance/refresh_scene.py) | Refreshes shading and camera setup in an existing baked blend file without rebaking physics |
| [`render_previews.py`](maintenance/render_previews.py) | Renders documentation preview images (`docs/assets/`) from an existing scene |
| [`plot_project_stats.py`](maintenance/plot_project_stats.py) | Generates repository line-count and architecture distribution charts |

