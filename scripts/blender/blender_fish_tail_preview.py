"""Standalone visual preview script for procedural salmon and tail swimming motion in Blender.

Creates a high-detail Atlantic salmon model with Geometry Nodes traveling wave tail motion,
lighting, camera framing, and playback timeline.

Usage:
    blender --python scripts/blender/blender_fish_tail_preview.py
    blender -b --python scripts/blender/blender_fish_tail_preview.py -o //preview_fish_ -F PNG -f 15
"""

from __future__ import annotations

import math
from pathlib import Path
import sys

import bpy

def _ensure_sim2blender_in_path() -> None:
    for start in [Path(__file__).resolve() if "__file__" in globals() and __file__ else Path.cwd().resolve()]:
        curr = start if start.is_dir() else start.parent
        for _ in range(6):
            src_dir = curr / "src"
            if (src_dir / "sim2blender").is_dir():
                src_str = str(src_dir)
                if src_str not in sys.path:
                    sys.path.insert(0, src_str)
                return
            if curr.parent == curr:
                break
            curr = curr.parent

_ensure_sim2blender_in_path()

from sim2blender.blender.fish.salmon import salmon_mesh
from sim2blender.blender.fish.tail_motion import apply_fish_tail_motion


def setup_preview_scene() -> None:
    # 1. Reset scene to clean state
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 25
    scene.frame_start = 1
    scene.frame_end = 100

    # 2. Add high-detail Atlantic salmon
    fish_length = 0.775
    mesh = salmon_mesh(length=fish_length)
    fish_obj = bpy.data.objects.new("Atlantic_Salmon_Preview", mesh)
    scene.collection.objects.link(fish_obj)

    # 3. Apply procedural tail swimming undulation (Geometry Nodes)
    apply_fish_tail_motion(
        fish_obj,
        amplitude_m=0.065,
        frequency_hz=2.2,
        wavelength_m=fish_length,
        phase_offset=0.0,
    )

    # 4. Camera framing
    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 50
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    cam_obj.location = (0.5, -1.2, 0.45)
    # Look slightly downwards at the fish center
    cam_obj.rotation_euler = (math.radians(72), math.radians(0), math.radians(22))

    # 5. Studio lighting
    light_key_data = bpy.data.lights.new("KeyLight", "SUN")
    light_key_data.energy = 3.5
    light_key_data.color = (0.9, 0.95, 1.0)
    light_key = bpy.data.objects.new("KeyLight", light_key_data)
    scene.collection.objects.link(light_key)
    light_key.rotation_euler = (math.radians(45), math.radians(15), math.radians(-30))

    light_fill_data = bpy.data.lights.new("FillLight", "SUN")
    light_fill_data.energy = 1.8
    light_fill_data.color = (0.6, 0.75, 0.85)
    light_fill = bpy.data.objects.new("FillLight", light_fill_data)
    scene.collection.objects.link(light_fill)
    light_fill.rotation_euler = (math.radians(-40), math.radians(-30), math.radians(120))

    print("Procedural salmon tail preview created successfully.")


if __name__ == "__main__":
    setup_preview_scene()
