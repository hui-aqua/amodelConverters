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
FISH_COUNT = 1000               # 鱼群数量 (尾 - 严格守恒，全程恒定无增减)
FISH_LENGTH_MEAN_M = 0.775     # 鱼体平均体长 (米, 均值 μ = 77.5 cm)
FISH_LENGTH_STD_M = 0.05       # 鱼群体长标准差 (米, 标准差 σ = 5.0 cm)
SWIM_SPEED_BL_S = 0.85         # 基准巡游速度 (BL/s, 0.85 体长/秒)
RANDOM_SEED = 7                # 鱼群随机运动种子

# Reynolds Boid 局部群体动力学
SEPARATION_WEIGHT = 0.35       # 邻近个体防碰撞排斥权重
SEPARATION_RADIUS_M = 1.2      # 防碰撞排斥作用半径 (m)
ALIGNMENT_WEIGHT = 0.25        # 邻近个体速度同向对齐权重
NEIGHBOR_RADIUS_M = 2.5        # 感知邻域对齐半径 (m)
SCHOOL_COHESION_WEIGHT = 0.15  # 局部鱼群集聚向心力权重

# 养殖网箱环形巡游与深度偏好 (Milling & Depth Band)
MILLING_WEIGHT = 0.45          # 环向切向巡游驱动力权重
CAGE_COHESION_WEIGHT = 0.08    # 网箱中心向心收拢权重
FLOW_DIRECTION = 1.0           # 巡游环流方向 (1.0 逆时针, -1.0 顺时针)
PREFERRED_DEPTH_MIN_M = -12.0  # 适宜游泳深度下界 (m)
PREFERRED_DEPTH_MAX_M = -2.5   # 适宜游泳深度上界 (m)
DEPTH_WEIGHT = 0.25            # 深度区间恢复力权重
VERTICAL_OSCILLATION_M = 0.35  # 自然垂向波动幅度 (m)

# 网衣边界平滑感知避碰与运动学约束 (Smooth Wall Avoidance & Kinematics)
WALL_DETECTION_DIST_M = 1.5    # 网衣预警感应距离 (m, 提前平滑转向避障)
WALL_AVOIDANCE_WEIGHT = 0.75   # 网衣避障法向推力权重
WALL_BUFFER_M = 0.05           # 网衣边界防穿透安全间距 (m)
MAX_TURN_RATE_DEG_S = 120.0    # 最大转向角速度限制 (°/s, 消除突变翻转)
SPECIES = "Atlantic salmon"    # 鱼类品种

# 水动力环境（海流与波浪）
CURRENT_SPEED_M_S = 0.20        # 水流流速 (m/s)
CURRENT_DIR_DEG = 45.0          # 水流方向 (度)
WAVE_HEIGHT_M = 0.40            # 波高 (m)
WAVE_PERIOD_S = 5.0             # 周期 (s)
WAVE_LENGTH_M = 25.0            # 波长 (m)
WAVE_DIR_DEG = 30.0             # 波浪传播方向 (度)
HYDRO_COUPLING = 0.35           # 水动力耦合强度 (0.0~1.0)
RHEOTAXIS_WEIGHT = 0.15         # 逆流趋流性对齐权重

# 尾鳍自主游动摆动 (Procedural Tail Swimming Undulation)
TAIL_MOTION = True             # 是否启用尾鳍游动摆动 (Geometry Nodes 行波变形)
TAIL_AMPLITUDE_M = 0.065       # 尾鳍横向最大摆动幅度 (m)
TAIL_FREQUENCY_HZ = 2.2        # 尾鳍游动摆动频率 (Hz)


def main() -> None:
    config = {
        "fish_count": FISH_COUNT,
        "fish_length_mean_m": FISH_LENGTH_MEAN_M,
        "fish_length_std_m": FISH_LENGTH_STD_M,
        "swim_speed_bl_s": SWIM_SPEED_BL_S,
        "random_seed": RANDOM_SEED,
        "separation_weight": SEPARATION_WEIGHT,
        "separation_radius_m": SEPARATION_RADIUS_M,
        "alignment_weight": ALIGNMENT_WEIGHT,
        "neighbor_radius_m": NEIGHBOR_RADIUS_M,
        "school_cohesion_weight": SCHOOL_COHESION_WEIGHT,
        "milling_weight": MILLING_WEIGHT,
        "cage_cohesion_weight": CAGE_COHESION_WEIGHT,
        "flow_direction": FLOW_DIRECTION,
        "preferred_depth_min_m": PREFERRED_DEPTH_MIN_M,
        "preferred_depth_max_m": PREFERRED_DEPTH_MAX_M,
        "depth_weight": DEPTH_WEIGHT,
        "vertical_oscillation_m": VERTICAL_OSCILLATION_M,
        "wall_detection_dist_m": WALL_DETECTION_DIST_M,
        "wall_avoidance_weight": WALL_AVOIDANCE_WEIGHT,
        "wall_buffer_m": WALL_BUFFER_M,
        "max_turn_rate_deg_s": MAX_TURN_RATE_DEG_S,
        "species": SPECIES,
        "current_speed_m_s": CURRENT_SPEED_M_S,
        "current_direction_deg": CURRENT_DIR_DEG,
        "wave_height_m": WAVE_HEIGHT_M,
        "wave_period_s": WAVE_PERIOD_S,
        "wave_length_m": WAVE_LENGTH_M,
        "wave_direction_deg": WAVE_DIR_DEG,
        "hydro_coupling": HYDRO_COUPLING,
        "rheotaxis_weight": RHEOTAXIS_WEIGHT,
        "tail_motion": TAIL_MOTION,
        "tail_amplitude_m": TAIL_AMPLITUDE_M,
        "tail_frequency_hz": TAIL_FREQUENCY_HZ,
    }
    run_fish_schooling(config)


if __name__ == "__main__":
    main()
