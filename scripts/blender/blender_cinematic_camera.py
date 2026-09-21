"""Set up automated cinematic camera movement in Blender.

This script creates an animated cinematic camera that transitions smoothly through
three distinct phases:
  1. High-angle aerial overview of the aquaculture net cage and rotating feed arm
  2. Medium glide-in swooping down directly above the feed spreader
  3. Diving below the water surface (Z < 0) to track sinking pellets and swarming fish

Can be run directly from Blender GUI Scripting workspace OR via Terminal command:
    blender scene.blend --python scripts/blender_cinematic_camera.py
"""

from __future__ import annotations

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

from sim2blender.blender.camera import setup_cinematic_camera, get_scene_focus_center

# -----------------------------------------------------------------------------
# 电影级运镜参数配置 (Cinematic Camera Configuration)
# -----------------------------------------------------------------------------
FOCAL_LENGTH_MM = 32.0          # 镜头焦距 (mm, 32mm 为自然微广角)
ENABLE_DEPTH_OF_FIELD = True    # 开启物理景深模拟 (自动跟踪焦点)
FSTOP = 3.5                     # 景深光圈大小 f-stop (推荐 2.8 ~ 5.6)

# 机位高度与距离微调
OVERVIEW_HEIGHT_M = 52.0        # 初始俯瞰航拍高度 (Z 轴高度)
OVERVIEW_DISTANCE_M = 104.0     # 初始全景与网箱中心的水平距离
WATER_ENTRY_DEPTH_M = -3.5      # 入水后潜水跟踪深度 (Z 轴负高度)


def main() -> None:
    config = {
        "focal_length_mm": FOCAL_LENGTH_MM,
        "enable_dof": ENABLE_DEPTH_OF_FIELD,
        "fstop": FSTOP,
        "overview_height_m": OVERVIEW_HEIGHT_M,
        "overview_distance_m": OVERVIEW_DISTANCE_M,
        "water_entry_depth_m": WATER_ENTRY_DEPTH_M,
    }
    setup_cinematic_camera(config)


if __name__ == "__main__":
    main()
