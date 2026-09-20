"""Automated multi-phase cinematic camera tracking and depth of field control.

Builds a dynamic look-at target and animates camera waypoints through three phases:
1. High-angle aerial overview of aquaculture cage
2. Medium glide-in swooping above feed spreader
3. Underwater dive tracking sinking pellets and swarming fish.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import sys

import bpy
from mathutils import Vector

FOCAL_LENGTH_MM = 32.0
ENABLE_DEPTH_OF_FIELD = True
FSTOP = 3.5

OVERVIEW_HEIGHT_M = 52.0
OVERVIEW_DISTANCE_M = 104.0
WATER_ENTRY_DEPTH_M = -3.5


def get_scene_focus_center() -> tuple[Vector, float]:
    """Calculate the focus center and approximate radius from cage or spreader."""
    spreader = bpy.data.objects.get("spreader_move") or bpy.data.objects.get("Feed_Rotor_30RPM")
    if spreader is not None:
        center = spreader.matrix_world.translation.copy()
        center.z = 0.0
        return center, 15.0

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


def setup_cinematic_camera(config: dict | None = None) -> None:
    """Set up multi-phase cinematic camera tracking with specified config."""
    cfg = config or {}
    focal_length = float(cfg.get("focal_length_mm", FOCAL_LENGTH_MM))
    enable_dof = bool(cfg.get("enable_depth_of_field", ENABLE_DEPTH_OF_FIELD))
    fstop = float(cfg.get("fstop", FSTOP))
    overview_h = float(cfg.get("overview_height_m", OVERVIEW_HEIGHT_M))
    overview_dist = float(cfg.get("overview_distance_m", OVERVIEW_DISTANCE_M))
    water_depth = float(cfg.get("water_entry_depth_m", WATER_ENTRY_DEPTH_M))
    phase1_pct = float(cfg.get("phase1_percent", 0.35))
    phase2_pct = float(cfg.get("phase2_percent", 0.60))
    clip_start = float(cfg.get("clip_start_m", 0.1))
    clip_end = float(cfg.get("clip_end_m", 500.0))
    swoop_h = float(cfg.get("swoop_height_m", 2.6))

    if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    f_start = scene.frame_start
    f_end = scene.frame_end
    total_frames = max(1, f_end - f_start)

    center, cage_radius = get_scene_focus_center()

    # 1. LookAt Target
    target = bpy.data.objects.get("Camera_LookAt_Target")
    if target is None:
        target = bpy.data.objects.new("Camera_LookAt_Target", None)
        target.empty_display_type = "SPHERE"
        target.empty_display_size = 0.6
        target.show_in_front = True
        scene.collection.objects.link(target)

    target.animation_data_clear()
    t_key_1 = f_start
    t_key_2 = f_start + int(total_frames * phase1_pct)
    t_key_3 = f_start + int(total_frames * min(0.99, phase2_pct + 0.05))
    t_key_4 = f_end

    target.location = center + Vector((0.0, 0.0, 0.5))
    target.keyframe_insert("location", frame=t_key_1)

    target.location = center + Vector((1.5, -0.8, -0.5))
    target.keyframe_insert("location", frame=t_key_2)

    target.location = center + Vector((2.8, -0.3, -2.0))
    target.keyframe_insert("location", frame=t_key_3)

    target.location = center + Vector((3.2, 0.2, -3.0))
    target.keyframe_insert("location", frame=t_key_4)

    # 2. Camera Object
    cam_obj = bpy.data.objects.get("Cinematic_Camera")
    if cam_obj is None:
        cam_data = bpy.data.cameras.new("Cinematic_Camera")
        cam_obj = bpy.data.objects.new("Cinematic_Camera", cam_data)
        scene.collection.objects.link(cam_obj)

    cam = cam_obj.data
    cam.lens = focal_length
    cam.clip_start = clip_start
    cam.clip_end = clip_end

    if enable_dof:
        cam.dof.use_dof = True
        cam.dof.focus_object = target
        cam.dof.aperture_fstop = fstop
    else:
        cam.dof.use_dof = False

    # 3. Track To constraint
    track = cam_obj.constraints.get("Track To Target")
    if track is None:
        track = cam_obj.constraints.new(type="TRACK_TO")
        track.name = "Track To Target"
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    # 4. Cinematic Waypoints
    cam_obj.animation_data_clear()

    f1 = f_start
    f2 = f_start + int(total_frames * phase1_pct)
    f3 = f_start + int(total_frames * phase2_pct)
    f4 = f_end

    r_factor = max(0.6, cage_radius / 15.0)
    pos_f1 = center + Vector((-0.7 * overview_dist * r_factor, -0.7 * overview_dist * r_factor, overview_h))
    pos_f2 = center + Vector((3.5 * r_factor, -5.2 * r_factor, swoop_h))
    pos_f3 = center + Vector((4.2 * r_factor, -3.8 * r_factor, -0.6))
    pos_f4 = center + Vector((5.8 * r_factor, -1.8 * r_factor, water_depth))

    waypoints = [
        (f1, pos_f1),
        (f2, pos_f2),
        (f3, pos_f3),
        (f4, pos_f4),
    ]

    for frame_idx, pos in waypoints:
        cam_obj.location = pos
        cam_obj.keyframe_insert("location", frame=frame_idx)

    # 5. Bezier interpolation
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

    scene.camera = cam_obj

    print(
        "CINEMATIC_CAMERA_DONE",
        f"Lens: {focal_length}mm",
        f"Frames: {f_start} -> {f_end}",
        f"Target: {target.name}",
    )
