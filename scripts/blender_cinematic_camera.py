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

import math
import os
from pathlib import Path
import sys

import bpy
from mathutils import Vector


# -----------------------------------------------------------------------------
# 电影级运镜参数配置 (Cinematic Camera Configuration)
# -----------------------------------------------------------------------------
FOCAL_LENGTH_MM = 32.0          # 镜头焦距 (mm, 32mm 为自然电影感微广角)
ENABLE_DEPTH_OF_FIELD = True    # 是否开启景深效果 (自动对焦到目标点)
FSTOP = 3.5                     # 景深光圈大小 (值越小虚化越强，推荐 2.8 ~ 5.6)

# 机位路径高度与相对距离微调
OVERVIEW_HEIGHT_M = 52.0        # 初始高空俯瞰高度 (Z 轴高度)
OVERVIEW_DISTANCE_M = 104.0      # 初始全景与中心的水平距离
WATER_ENTRY_DEPTH_M = -3.5      # 入水后最终水下观察深度 (Z 轴负高度)


def get_scene_focus_center() -> tuple[Vector, float]:
    """Calculate the focus center and approximate radius from cage or spreader."""
    # Try finding spreader_move or Feed_Rotor_30RPM
    spreader = bpy.data.objects.get("spreader_move") or bpy.data.objects.get("Feed_Rotor_30RPM")
    if spreader is not None:
        center = spreader.matrix_world.translation.copy()
        center.z = 0.0
        return center, 15.0

    # Try finding Membrane cage
    cage = bpy.data.objects.get("Membrane cage")
    if cage is not None and cage.type == "MESH" and cage.data.vertices:
        matrix = cage.matrix_world
        verts = [matrix @ v.co for v in cage.data.vertices]
        low = Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
        high = Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
        center = (low + high) * 0.5
        center.z = 0.0
        radius = max((high - low).length * 0.5, 8.0)
        return center, radius

    return Vector((0.0, 0.0, 0.0)), 15.0


def setup_cinematic_camera() -> None:
    if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    f_start = scene.frame_start
    f_end = scene.frame_end
    total_frames = max(1, f_end - f_start)

    center, cage_radius = get_scene_focus_center()

    # 1. 创建或获取相机聚焦目标点 (LookAt Target)
    target = bpy.data.objects.get("Camera_LookAt_Target")
    if target is None:
        target = bpy.data.objects.new("Camera_LookAt_Target", None)
        target.empty_display_type = "SPHERE"
        target.empty_display_size = 0.6
        target.show_in_front = True
        scene.collection.objects.link(target)

    # 动态给目标点插入平滑关键帧：跟随视觉重心从撒料机慢慢下沉至水下鱼群抢食区
    target.animation_data_clear()
    t_key_1 = f_start
    t_key_2 = f_start + int(total_frames * 0.35)
    t_key_3 = f_start + int(total_frames * 0.65)
    t_key_4 = f_end

    target.location = center + Vector((0.0, 0.0, 0.5))
    target.keyframe_insert("location", frame=t_key_1)

    target.location = center + Vector((1.5, -0.8, -0.5))
    target.keyframe_insert("location", frame=t_key_2)

    target.location = center + Vector((2.8, -0.3, -2.0))
    target.keyframe_insert("location", frame=t_key_3)

    target.location = center + Vector((3.2, 0.2, -3.0))
    target.keyframe_insert("location", frame=t_key_4)

    # 2. 创建或更新电影摄影机对象
    cam_obj = bpy.data.objects.get("Cinematic_Camera")
    if cam_obj is None:
        cam_data = bpy.data.cameras.new("Cinematic_Camera")
        cam_obj = bpy.data.objects.new("Cinematic_Camera", cam_data)
        scene.collection.objects.link(cam_obj)

    cam = cam_obj.data
    cam.lens = FOCAL_LENGTH_MM
    cam.clip_start = 0.1
    cam.clip_end = 500.0

    # 景深配置
    if ENABLE_DEPTH_OF_FIELD:
        cam.dof.use_dof = True
        cam.dof.focus_object = target
        cam.dof.aperture_fstop = FSTOP
    else:
        cam.dof.use_dof = False

    # 3. 设置 Track To 约束（让镜头始终平滑锁定 Target）
    track = cam_obj.constraints.get("Track To Target")
    if track is None:
        track = cam_obj.constraints.new(type="TRACK_TO")
        track.name = "Track To Target"
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    # 4. 设计三段式电影运镜路径关键帧
    cam_obj.animation_data_clear()

    # 关键帧时间节点
    f1 = f_start                             # 阶段 1: 全景俯瞰起幅
    f2 = f_start + int(total_frames * 0.35)  # 阶段 2: 掠过撒料臂上方
    f3 = f_start + int(total_frames * 0.60)  # 阶段 3: 穿透水面入水时刻 (Z = -0.5m)
    f4 = f_end                               # 阶段 4: 水下仰视跟踪饲料与鱼群抢食

    # 依据网箱尺寸缩放机位坐标
    r_factor = max(0.6, cage_radius / 15.0)
    pos_f1 = center + Vector((-0.7 * OVERVIEW_DISTANCE_M * r_factor, -0.7 * OVERVIEW_DISTANCE_M * r_factor, OVERVIEW_HEIGHT_M))
    pos_f2 = center + Vector((3.5 * r_factor, -5.2 * r_factor, 2.6))
    pos_f3 = center + Vector((4.2 * r_factor, -3.8 * r_factor, -0.6))
    pos_f4 = center + Vector((5.8 * r_factor, -1.8 * r_factor, WATER_ENTRY_DEPTH_M))

    waypoints = [
        (f1, pos_f1),
        (f2, pos_f2),
        (f3, pos_f3),
        (f4, pos_f4),
    ]

    for frame_idx, pos in waypoints:
        cam_obj.location = pos
        cam_obj.keyframe_insert("location", frame=frame_idx)

    # 5. 设置平滑贝塞尔曲线插值 (BEZIER + EASE_IN_OUT)
    for obj in (cam_obj, target):
        if obj.animation_data and obj.animation_data.action:
            action = obj.animation_data.action
            curves = []
            if hasattr(action, "fcurves"):
                curves = action.fcurves
            elif hasattr(action, "layers"):
                for layer in action.layers:
                    for strip in layer.strips:
                        for bag in strip.channelbags:
                            curves.extend(bag.fcurves)
            for curve in curves:
                for keypoint in curve.keyframe_points:
                    keypoint.interpolation = "BEZIER"
                    keypoint.easing = "EASE_IN_OUT"

    # 6. 将其激活为当前场景主摄像机
    scene.camera = cam_obj

    print(
        "CINEMATIC_CAMERA_DONE",
        f"Lens: {FOCAL_LENGTH_MM}mm",
        f"Frames: {f_start} -> {f_end}",
        f"Target: {target.name}",
    )


if __name__ == "__main__":
    setup_cinematic_camera()
