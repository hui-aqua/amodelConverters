"""Coupled fish school swimming and feed pellet ingestion dynamics.

Finds the net enclosure, identifies water-borne feed particles emitted by
the feed spreader, and models salmon satiety, sensory attraction, sprint bursts,
and pellet consumption.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import random
import sys

import bmesh
import bpy
from mathutils import Vector, Quaternion

from sim2blender.blender.enclosure import Enclosure, boundary_caps, stitch_membrane_seams
from sim2blender.blender.fish.salmon import salmon_mesh

FISH_COUNT = 1000
FISH_LENGTH_MEAN_M = 0.775
FISH_LENGTH_STD_M = 0.05

SWIM_SPEED_BL_S = 0.85
FEEDING_SPEED_BL_S = 2.0

SENSING_RADIUS_M = 2.5
INGESTION_RADIUS_M = 0.22
FEEDING_COOLDOWN_S = 10.0
ATTRACTION_WEIGHT = 0.55
WATER_LEVEL_Z = 0.0
RANDOM_SEED = 7


def cleanup_existing_fish_school() -> None:
    """Clear previously generated 'Fish school' collection and fish objects."""
    old_school = bpy.data.collections.get("Fish school")
    if old_school is not None:
        for old_obj in list(old_school.objects):
            bpy.data.objects.remove(old_obj, do_unlink=True)
        bpy.data.collections.remove(old_school)

    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith("salmon") or mesh.name.startswith("Fish_"):
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def find_membrane_cage_object() -> bpy.types.Object:
    """Find the 'Membrane cage' object inside 'AModel cage' collection or scene."""
    collection = bpy.data.collections.get("AModel cage")
    if collection is not None:
        obj = collection.objects.get("Membrane cage")
        if obj is not None:
            return obj
        for o in collection.objects:
            if o.type == "MESH" and ("membrane" in o.name.lower() or "cage" in o.name.lower()):
                return o

    obj = bpy.data.objects.get("Membrane cage")
    if obj is not None:
        return obj

    for o in bpy.data.objects:
        if o.type == "MESH":
            name_lower = o.name.lower()
            if "membrane" in name_lower or "cage" in name_lower:
                return o

    raise RuntimeError(
        "Could not find 'Membrane cage' object in 'AModel cage' collection.\n"
        "Please ensure your Blender scene contains the net cage mesh."
    )


def build_enclosure_from_cage(cage_obj: bpy.types.Object) -> Enclosure:
    """Construct a 3D BVH Enclosure from the cage mesh geometry for boundary checking."""
    mesh = cage_obj.data
    matrix = cage_obj.matrix_world
    points = [matrix @ v.co for v in mesh.vertices]
    faces = [tuple(p.vertices) for p in mesh.polygons]

    faces_stitched = stitch_membrane_seams(faces, points)
    try:
        caps = boundary_caps(faces_stitched, points, allow_caps=True)
    except Exception:
        caps = []

    return Enclosure(points, faces_stitched + caps)


def get_feed_particle_objects() -> list[bpy.types.Object]:
    """Retrieve all animated feed pellet objects in the scene."""
    collection = bpy.data.collections.get("FishFeed_Proxy_Particles")
    if collection is None:
        return []
    return [obj for obj in collection.objects if obj.type == "MESH"]


def run_fish_feeding_animation(config: dict | None = None) -> None:
    """Execute coupled fish schooling and feeding interaction animation."""
    cfg = config or {}
    count = int(cfg.get("fish_count", FISH_COUNT))
    mean_length = float(cfg.get("fish_length_mean_m", FISH_LENGTH_MEAN_M))
    std_length = float(cfg.get("fish_length_std_m", FISH_LENGTH_STD_M))
    cruise_speed_bl = float(cfg.get("swim_speed_bl_s", SWIM_SPEED_BL_S))
    feeding_speed_bl = float(cfg.get("feeding_speed_bl_s", FEEDING_SPEED_BL_S))
    sensing_radius = float(cfg.get("sensing_radius_m", SENSING_RADIUS_M))
    ingestion_radius = float(cfg.get("ingestion_radius_m", INGESTION_RADIUS_M))
    feeding_cooldown = float(cfg.get("feeding_cooldown_s", FEEDING_COOLDOWN_S))
    attraction_weight = float(cfg.get("attraction_weight", ATTRACTION_WEIGHT))
    water_level_z = float(cfg.get("water_level_z", WATER_LEVEL_Z))
    seed = int(cfg.get("random_seed", RANDOM_SEED))
    species_name = str(cfg.get("species", "Atlantic salmon"))

    if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    frame_start = scene.frame_start
    frame_end = scene.frame_end

    cleanup_existing_fish_school()

    cage_obj = find_membrane_cage_object()
    enclosure = build_enclosure_from_cage(cage_obj)
    cage_center = (enclosure.low + enclosure.high) * 0.5

    rng = random.Random(seed)

    school_collection = bpy.data.collections.new("Fish school")
    scene.collection.children.link(school_collection)

    template_mesh = salmon_mesh(mean_length)
    base_clearance = max(v.co.length for v in template_mesh.vertices) + mean_length * 1e-5

    fish_objects: list[bpy.types.Object] = []
    positions: list[Vector] = []
    velocities: list[Vector] = []
    fish_cruise_speeds: list[float] = []
    fish_feeding_speeds: list[float] = []
    fish_clearances: list[float] = []
    last_eat_time: list[float] = [-999.0] * count

    for i in range(count):
        raw_length = rng.gauss(mean_length, std_length)
        min_length = max(0.1, mean_length - 3.0 * std_length)
        max_length = mean_length + 3.0 * std_length
        length_i = max(min_length, min(max_length, raw_length))

        cruise_speed_i = cruise_speed_bl * length_i
        feeding_speed_i = feeding_speed_bl * length_i
        clearance_i = base_clearance * (length_i / mean_length)

        fish_cruise_speeds.append(cruise_speed_i)
        fish_feeding_speeds.append(feeding_speed_i)
        fish_clearances.append(clearance_i)

        fish_obj = bpy.data.objects.new(f"Fish_{i + 1:03d}", template_mesh)
        school_collection.objects.link(fish_obj)
        fish_obj.rotation_mode = "QUATERNION"

        scale_ratio = length_i / mean_length
        fish_obj.scale = (scale_ratio, scale_ratio, scale_ratio)
        fish_obj["fish_species"] = species_name
        fish_obj["fish_length_m"] = length_i
        fish_objects.append(fish_obj)

        pos = enclosure.sample(rng, clearance_i)
        positions.append(pos)

        angle = rng.uniform(0, math.tau)
        vel = Vector((math.cos(angle), math.sin(angle), rng.uniform(-0.1, 0.1))).normalized()
        velocities.append(vel)

    min_depth = float(cfg.get("min_feeding_depth_m", -25.0))
    max_depth = float(cfg.get("max_feeding_depth_m", water_level_z))

    # Resolve hydrodynamics from config, falling back to scene properties if available
    current_speed = float(cfg.get("current_speed_m_s", cfg.get("current_speed", scene.get("current_speed_m_s", 0.0))))
    current_dir_deg = float(cfg.get("current_direction_deg", cfg.get("current_dir_deg", scene.get("current_direction_deg", 0.0))))
    wave_height = float(cfg.get("wave_height_m", cfg.get("wave_height", scene.get("wave_height_m", 0.0))))
    wave_period = float(cfg.get("wave_period_s", cfg.get("wave_period", scene.get("wave_period_s", 5.0))))
    wave_length = float(cfg.get("wave_length_m", cfg.get("wave_length", scene.get("wave_length_m", 30.0))))
    wave_dir_deg = float(cfg.get("wave_direction_deg", cfg.get("wave_dir_deg", scene.get("wave_direction_deg", 0.0))))
    water_level = float(cfg.get("water_level_m", cfg.get("water_level", scene.get("water_level_z", water_level_z))))
    hydro_coupling = float(cfg.get("hydro_coupling", 0.35))

    feed_particles = get_feed_particle_objects()
    consumed_frames: dict[bpy.types.Object, float] = {}

    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        elapsed_s = (frame - frame_start) / fps

        active_feed_positions: list[Vector] = []
        for pellet in feed_particles:
            if pellet in consumed_frames:
                continue
            loc = pellet.location.copy()
            if min_depth <= loc.z <= max_depth:
                active_feed_positions.append(loc)

        for i, fish_obj in enumerate(fish_objects):
            p = positions[i]
            v = velocities[i]
            clearance_i = fish_clearances[i]

            is_satiated = (elapsed_s - last_eat_time[i]) < feeding_cooldown

            radial = p - cage_center
            cruise_dir = Vector((-radial.y, radial.x, math.sin(elapsed_s * 0.9 + i) * 0.35))
            cruise_dir += (cage_center - p) * 0.08
            if cruise_dir.length < 1e-8:
                cruise_dir = Vector((1.0, 0.0, 0.0))
            cruise_dir.normalize()

            target_feed_pos: Vector | None = None
            min_dist = sensing_radius

            if not is_satiated:
                for feed_pos in active_feed_positions:
                    dist = (feed_pos - p).length
                    if dist < min_dist:
                        min_dist = dist
                        target_feed_pos = feed_pos

                    if dist <= ingestion_radius and feed_particles:
                        for pellet in feed_particles:
                            if (pellet.location - feed_pos).length < 1e-3 and pellet not in consumed_frames:
                                consumed_frames[pellet] = float(frame)
                                last_eat_time[i] = elapsed_s
                                break

            if target_feed_pos is not None:
                attraction_dir = (target_feed_pos - p).normalized()
                desired_dir = (cruise_dir * (1.0 - attraction_weight) + attraction_dir * attraction_weight).normalized()
                current_speed = fish_feeding_speeds[i]
            else:
                desired_dir = cruise_dir
                current_speed = fish_cruise_speeds[i]

            swim_vec = (v * 0.82 + desired_dir * 0.18).normalized() * (current_speed / fps if frame > frame_start else 0.0)

            # Ambient hydrodynamic velocity (current advection + wave orbital kinematics)
            if (current_speed > 0.0 or wave_height > 0.0) and frame > frame_start:
                from sim2blender.blender.environment import calculate_water_velocity
                v_water = calculate_water_velocity(
                    p, elapsed_s,
                    current_speed=current_speed,
                    current_dir_deg=current_dir_deg,
                    wave_height=wave_height,
                    wave_period=wave_period,
                    wave_length=wave_length,
                    wave_dir_deg=wave_dir_deg,
                    water_level=water_level,
                )
                water_step = (v_water / fps) * hydro_coupling
            else:
                water_step = Vector((0.0, 0.0, 0.0))

            total_step = swim_vec + water_step
            step_length = total_step.length
            direction = total_step.normalized() if step_length > 1e-6 else v

            target_p = p + total_step
            if enclosure.contains(p, clearance_i + step_length) and enclosure.contains(target_p, clearance_i):
                p = target_p
            else:
                direction = (cage_center - p).normalized()
                target_p = p + direction * (step_length * 0.5)
                if enclosure.contains(target_p, clearance_i):
                    p = target_p

            positions[i] = p
            velocities[i] = direction

            fish_obj.location = p
            fish_obj.rotation_quaternion = direction.to_track_quat("X", "Z")
            fish_obj.keyframe_insert("location", frame=frame)
            fish_obj.keyframe_insert("rotation_quaternion", frame=frame)

        if frame == frame_start or frame % 20 == 0:
            print(f"Validated {count} feeding fish at frame {frame}/{frame_end}", flush=True)

    for fish_obj in fish_objects:
        if fish_obj.animation_data and fish_obj.animation_data.action:
            action = fish_obj.animation_data.action
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
                    keypoint.interpolation = "CONSTANT"

    for pellet, eat_frame in consumed_frames.items():
        emit_time = pellet.get("emission_time_s", 0.0)
        emit_frame = frame_start + emit_time * fps
        for prop in ("hide_viewport", "hide_render"):
            try:
                driver = pellet.driver_add(prop).driver
                driver.type = "SCRIPTED"
                driver.expression = f"frame < {emit_frame:.8f} or frame > {eat_frame:.8f}"
            except Exception:
                pass

    scene["fish_count"] = count
    scene["fish_length_mean_m"] = mean_length
    scene["fish_length_std_m"] = std_length
    scene["fish_consumed_pellets"] = len(consumed_frames)

    print(
        "FISH_FEEDING_ANIMATION_DONE",
        "FISH_COUNT", count,
        "CONSUMED_PELLETS", len(consumed_frames),
    )
