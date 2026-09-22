"""Fixed Underwater Feeding Camera and Pyramid Frustum Pellet Counter in Blender.

Sets up a fixed camera at (X, Y, Z), points it at a target, draws the 3D visible pyramid
volume up to the visual distance (FHD 16:9), and counts passing feed pellets.

Can be run inside Blender's Scripting workspace OR via Terminal:
    blender scene.blend --python scripts/blender/blender_feeding_camera.py
    blender scene.blend --python scripts/blender/blender_feeding_camera.py -- --pos-x 2.5 --pos-z -5.0 --visual-distance 2.5
"""

from __future__ import annotations

import argparse
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

from sim2blender.blender.feeding_camera import (
    DEFAULT_FEEDING_CAMERA_CONFIG,
    setup_feeding_camera,
    count_pellets_in_frustum,
)


def parse_arguments() -> argparse.Namespace:
    argv = sys.argv
    cli_args = argv[argv.index("--") + 1:] if "--" in argv else []

    parser = argparse.ArgumentParser(description="Sim2Blender Feeding Camera & Frustum Pellet Counter")
    parser.add_argument("--pos-x", type=float, default=2.5, help="Camera position X (m)")
    parser.add_argument("--pos-y", type=float, default=0.0, help="Camera position Y (m)")
    parser.add_argument("--pos-z", type=float, default=-5.0, help="Camera position Z (m)")
    parser.add_argument("--look-at-x", type=float, default=0.0, help="Look-At target X (m)")
    parser.add_argument("--look-at-y", type=float, default=0.0, help="Look-At target Y (m)")
    parser.add_argument("--look-at-z", type=float, default=-5.0, help="Look-At target Z (m)")
    parser.add_argument("--visual-distance", type=float, default=2.5, help="Visual range / far clip (m)")
    parser.add_argument("--focal-length", type=float, default=32.0, help="Focal length (mm)")
    parser.add_argument("--no-frustum", action="store_true", help="Do not generate frustum pyramid mesh")
    parser.add_argument("--no-hud", action="store_true", help="Do not create 3D text counter HUD")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output report JSON path")
    return parser.parse_args(cli_args)


def main() -> None:
    args = parse_arguments()
    config = {
        "position_x": args.pos_x,
        "position_y": args.pos_y,
        "position_z": args.pos_z,
        "look_at_x": args.look_at_x,
        "look_at_y": args.look_at_y,
        "look_at_z": args.look_at_z,
        "visual_distance_m": args.visual_distance,
        "focal_length_mm": args.focal_length,
        "show_frustum_pyramid": not args.no_frustum,
        "show_hud_counter": not args.no_hud,
    }

    cam_obj, frustum_obj, hud_obj = setup_feeding_camera(config)
    scene = bpy.context.scene

    out_path = args.output
    if out_path is None and bpy.data.filepath:
        out_path = Path(bpy.data.filepath)

    report = count_pellets_in_frustum(scene, cam_obj, config, out_path)
    print(
        f"Summary: {report['total_unique_pellets_detected']} unique pellets detected "
        f"within {report['visual_distance_m']}m pyramid frustum."
    )


if __name__ == "__main__":
    main()
