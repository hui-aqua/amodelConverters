"""Build a 30 RPM rotating feed arm and a 30 kg/min visual feed stream in Blender.

This script imports 'spreader_move.obj' and 'spreader_still.obj' (by default from
assets/spreaders/default/), parents the moving arm to a continuous rotor, and bakes ballistic
feed pellets across air and water fluid media.

Can be run directly from Blender GUI Scripting workspace OR via Terminal:
    blender scene.blend --python scripts/blender_feed_animation.py
"""

from __future__ import annotations

import os
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

from sim2blender.blender.feed import (
    DEFAULT_SPREADER_MOVE_PATH,
    DEFAULT_SPREADER_STILL_PATH,
    run_feed_animation,
)

# -----------------------------------------------------------------------------
# 撒料机与饲料颗粒配置参数 (Spreader & Feed Particle Configuration)
# -----------------------------------------------------------------------------
SPREADER_MOVE_OBJ = DEFAULT_SPREADER_MOVE_PATH
SPREADER_STILL_OBJ = DEFAULT_SPREADER_STILL_PATH

RPM = -30.0                   # 旋转臂转速 (RPM, 负值顺时针，正值逆时针)
MASS_FLOW_KG_MIN = 30.0       # 饲料总质量流量 (kg/min)
VISUAL_PARTICLE_MASS_KG = 0.01# 单个视觉代理颗粒质量 (kg)
PARTICLE_LIFETIME_S = 30.0    # 颗粒存活时间 (秒)

PELLET_RADIUS_MEAN_M = 0.005  # 颗粒圆柱半径均值 (米)
PELLET_RADIUS_STD_M = 0.0008  # 颗粒圆柱半径标准差 (米)
PELLET_ASPECT_RATIO = 1.6     # 颗粒长径比 (高度 / 直径)

OUTWARD_SPEED_M_S = 1.0       # 径向向外抛洒速度 (m/s)
DOWNWARD_SPEED_M_S = 0.001    # 向下垂直初速度 (m/s)
RANDOM_SEED = 30030           # 随机散射种子

# 双介质流体物性参数
WATER_LEVEL_Z = 0.0           # 水面高度 (米, Z <= 0 为水下)
PELLET_DENSITY_KG_M3 = 1100.0 # 饲料颗粒密度 (kg/m³)
AIR_DRAG_COEFF = 0.47         # 空气阻力系数
WATER_DRAG_COEFF = 0.85       # 水中阻力系数

# 水动力环境（海流与波浪）
CURRENT_SPEED_M_S = 0.25      # 水流流速 (m/s)
CURRENT_DIR_DEG = 45.0        # 水流方向 (度, 0=+X, 90=+Y)
WAVE_HEIGHT_M = 0.40          # 波高 (m)
WAVE_PERIOD_S = 5.0           # 周期 (s)
WAVE_LENGTH_M = 25.0          # 波长 (m)
WAVE_DIR_DEG = 30.0           # 波浪传播方向 (度)


def main() -> None:
    config = {
        "spreader_move_obj": SPREADER_MOVE_OBJ,
        "spreader_still_obj": SPREADER_STILL_OBJ,
        "rpm": RPM,
        "mass_flow_kg_min": MASS_FLOW_KG_MIN,
        "visual_particle_mass_kg": VISUAL_PARTICLE_MASS_KG,
        "particle_lifetime_s": PARTICLE_LIFETIME_S,
        "pellet_radius_mean_m": PELLET_RADIUS_MEAN_M,
        "pellet_radius_std_m": PELLET_RADIUS_STD_M,
        "pellet_aspect_ratio": PELLET_ASPECT_RATIO,
        "outward_speed_m_s": OUTWARD_SPEED_M_S,
        "downward_speed_m_s": DOWNWARD_SPEED_M_S,
        "random_seed": RANDOM_SEED,
        "water_level_z": WATER_LEVEL_Z,
        "pellet_density_kg_m3": PELLET_DENSITY_KG_M3,
        "air_drag_coeff": AIR_DRAG_COEFF,
        "water_drag_coeff": WATER_DRAG_COEFF,
        "current_speed_m_s": CURRENT_SPEED_M_S,
        "current_direction_deg": CURRENT_DIR_DEG,
        "wave_height_m": WAVE_HEIGHT_M,
        "wave_period_s": WAVE_PERIOD_S,
        "wave_length_m": WAVE_LENGTH_M,
        "wave_direction_deg": WAVE_DIR_DEG,
    }
    run_feed_animation(config)

    current_path = bpy.data.filepath
    if current_path:
        folder = os.path.dirname(current_path) or os.getcwd()
        stem = os.path.splitext(os.path.basename(current_path))[0]
        if not stem.endswith("_feed"):
            stem += "_feed"
        save_path = os.path.join(folder, stem + ".blend")
        bpy.ops.wm.save_as_mainfile(filepath=save_path, check_existing=False)


if __name__ == "__main__":
    main()
