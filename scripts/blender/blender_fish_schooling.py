"""Bake simple boid fish schooling animation contained in the net cage.

This script finds the 'Membrane cage' object, builds the 3D boundary enclosure,
and simulates deterministic boid fish schooling contained within the cage.

Can be run directly from Blender GUI Scripting workspace OR via Terminal command:
    blender scene.blend --python scripts/blender_fish_schooling.py
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

from sim2blender.blender.fish.school import (
    run_fish_schooling,
    cleanup_existing_fish_school,
    find_membrane_cage_object,
    build_enclosure_from_cage,
)

# -----------------------------------------------------------------------------
# 鱼群仿真参数配置 (Fish Schooling Configuration)
# -----------------------------------------------------------------------------
FISH_COUNT = 1000               # 鱼群数量 (尾)
FISH_LENGTH_MEAN_M = 0.775     # 鱼体平均体长 (米, 均值 μ = 77.5 cm)
FISH_LENGTH_STD_M = 0.05       # 鱼群体长标准差 (米, 标准差 σ = 5.0 cm)
SWIM_SPEED_BL_S = 0.85         # 基准巡游速度 (BL/s, 0.85 体长/秒)
RANDOM_SEED = 7                # 鱼群随机运动种子
COHESION_WEIGHT = 0.08         # 鱼群向心聚集权重
VERTICAL_OSCILLATION_M = 0.35  # 垂直波动幅度 (m)
FLOW_DIRECTION = 1.0           # 巡游环流方向 (1.0 逆时针, -1.0 顺时针)
WALL_BUFFER_M = 0.05           # 网衣边界防穿透缓冲间距 (m)
SPECIES = "Atlantic salmon"    # 鱼类品种

# 水动力环境（海流与波浪）
CURRENT_SPEED_M_S = 0.20        # 水流流速 (m/s)
CURRENT_DIR_DEG = 45.0          # 水流方向 (度)
WAVE_HEIGHT_M = 0.40            # 波高 (m)
WAVE_PERIOD_S = 5.0             # 周期 (s)
WAVE_LENGTH_M = 25.0            # 波长 (m)
WAVE_DIR_DEG = 30.0             # 波浪传播方向 (度)
HYDRO_COUPLING = 0.35           # 水动力耦合强度 (0.0~1.0)


def main() -> None:
    config = {
        "fish_count": FISH_COUNT,
        "fish_length_mean_m": FISH_LENGTH_MEAN_M,
        "fish_length_std_m": FISH_LENGTH_STD_M,
        "swim_speed_bl_s": SWIM_SPEED_BL_S,
        "random_seed": RANDOM_SEED,
        "cohesion_weight": COHESION_WEIGHT,
        "vertical_oscillation_m": VERTICAL_OSCILLATION_M,
        "flow_direction": FLOW_DIRECTION,
        "wall_buffer_m": WALL_BUFFER_M,
        "species": SPECIES,
        "current_speed_m_s": CURRENT_SPEED_M_S,
        "current_direction_deg": CURRENT_DIR_DEG,
        "wave_height_m": WAVE_HEIGHT_M,
        "wave_period_s": WAVE_PERIOD_S,
        "wave_length_m": WAVE_LENGTH_M,
        "wave_direction_deg": WAVE_DIR_DEG,
        "hydro_coupling": HYDRO_COUPLING,
    }
    run_fish_schooling(config)


if __name__ == "__main__":
    main()
