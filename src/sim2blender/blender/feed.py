"""Feed spreader kinematics and dual-medium ballistic pellet dynamics.

Imports or locates the feed spreader arm and stationary base, sets up the
continuous rotation driver, and integrates air/water ballistic trajectories
considering aerodynamic drag, hydrodynamic drag, buoyancy, and damping.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import random
import sys

import bmesh
import bpy
from mathutils import Vector

from sim2blender.core.paths import PROJECT_ROOT

DEFAULT_SPREADER_MOVE_PATH = str(PROJECT_ROOT / "examples/models/spreader_move.obj")
DEFAULT_SPREADER_STILL_PATH = str(PROJECT_ROOT / "examples/models/spreader_still.obj")

RPM = -30.0
MASS_FLOW_KG_MIN = 30.0
VISUAL_PARTICLE_MASS_KG = 0.01
PARTICLE_LIFETIME_S = 30.0

PELLET_RADIUS_MEAN_M = 0.005
PELLET_RADIUS_STD_M = 0.0008
PELLET_ASPECT_RATIO = 1.6

OUTWARD_SPEED_M_S = 1.0
DOWNWARD_SPEED_M_S = 0.001
GRAVITY_M_S2 = 9.81
RANDOM_SEED = 30030

WATER_LEVEL_Z = 0.0
PELLET_DENSITY_KG_M3 = 1100.0
AIR_DENSITY_KG_M3 = 1.225
WATER_DENSITY_KG_M3 = 1000.0
AIR_DRAG_COEFF = 0.47
WATER_DRAG_COEFF = 0.85
WATER_SPIN_DAMPING = 1.0


def import_obj_file(filepath: str | Path) -> list[bpy.types.Object]:
    """Import OBJ file into Blender with cross-version compatibility."""
    path = Path(filepath).resolve()
    if not path.is_file():
        return []
    before = set(bpy.data.objects)
    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=str(path))
    elif hasattr(bpy.ops.import_scene, "obj"):
        bpy.ops.import_scene.obj(filepath=str(path))
    else:
        return []
    return [o for o in bpy.data.objects if o not in before]


def find_or_import_spreader_move_object(
    move_obj_path: str | Path | None = None,
    still_obj_path: str | Path | None = None,
) -> bpy.types.Object:
    """Find existing 'spreader_move' or import from obj paths."""
    obj = bpy.data.objects.get("spreader_move")
    if obj is not None:
        return obj

    for o in bpy.data.objects:
        name_lower = o.name.lower()
        if "spreader" in name_lower and "move" in name_lower:
            return o

    still_p = Path(still_obj_path or DEFAULT_SPREADER_STILL_PATH).resolve()
    if still_p.is_file() and not bpy.data.objects.get("spreader_still"):
        imported_still = import_obj_file(still_p)
        for o in imported_still:
            if o.type == "MESH":
                o.name = "spreader_still"

    move_p = Path(move_obj_path or DEFAULT_SPREADER_MOVE_PATH).resolve()
    if move_p.is_file():
        imported_move = import_obj_file(move_p)
        for o in imported_move:
            if o.type == "MESH":
                o.name = "spreader_move"
                return o

    obj = bpy.data.objects.get("spreader_move")
    if obj is not None:
        return obj

    available = [o.name for o in bpy.data.objects if "spreader" in o.name.lower()]
    hint = f" Found related objects: {available}" if available else ""
    raise RuntimeError(
        f"Could not find or import 'spreader_move' object in Blender scene.{hint}\n"
        f"Checked path: {move_p}"
    )


def find_spreader_outlet_tip(spreader_obj: bpy.types.Object) -> Vector:
    """Determine the outlet tip coordinates from the spreader_move geometry."""
    outlet_obj = bpy.data.objects.get("FishFeed_Outlet_30kgmin")
    if outlet_obj is not None:
        return outlet_obj.location.copy()

    if spreader_obj.type == "MESH" and spreader_obj.data.vertices:
        matrix = spreader_obj.matrix_world
        world_verts = [matrix @ v.co for v in spreader_obj.data.vertices]

        radii = [math.hypot(v.x, v.y) for v in world_verts]
        max_r = max(radii)

        tip_verts = [v for v, r in zip(world_verts, radii) if r >= max_r - 0.05]
        if tip_verts:
            return sum(tip_verts, Vector()) / len(tip_verts)
        return sum(world_verts, Vector()) / len(world_verts)

    return spreader_obj.matrix_world.translation.copy()


def make_pellet_mesh(
    radius_mean: float = PELLET_RADIUS_MEAN_M,
    aspect_ratio: float = PELLET_ASPECT_RATIO,
) -> bpy.types.Mesh:
    """Create a realistic cylindrical feed pellet mesh."""
    mesh = bpy.data.meshes.new("FishFeed_Pellet_Mesh")
    bm = bmesh.new()
    cylinder_height = (radius_mean * 2.0) * aspect_ratio
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=12,
        radius1=radius_mean,
        radius2=radius_mean,
        depth=cylinder_height,
    )
    bm.to_mesh(mesh)
    bm.free()

    material = bpy.data.materials.get("FishFeed_Brown")
    if material is None:
        material = bpy.data.materials.new("FishFeed_Brown")
        material.diffuse_color = (0.34, 0.12, 0.025, 1.0)
        material.use_nodes = True
        shader = material.node_tree.nodes.get("Principled BSDF")
        if shader is not None:
            shader.inputs["Base Color"].default_value = (0.34, 0.12, 0.025, 1.0)
            shader.inputs["Roughness"].default_value = 0.82
    mesh.materials.append(material)
    return mesh


def set_interpolation(obj: bpy.types.Object) -> None:
    action = obj.animation_data.action if obj.animation_data else None
    if action is None or not hasattr(action, "fcurves"):
        return
    for curve in action.fcurves:
        interpolation = "CONSTANT" if curve.data_path == "scale" else "LINEAR"
        for keyframe in curve.keyframe_points:
            keyframe.interpolation = interpolation


def compute_particle_trajectory(
    start_pos: Vector,
    start_vel: Vector,
    start_spin: Vector,
    initial_rot: Vector,
    duration_s: float,
    radius_m: float = PELLET_RADIUS_MEAN_M,
    aspect_ratio: float = PELLET_ASPECT_RATIO,
    dt_s: float = 0.005,
    water_level_z: float = WATER_LEVEL_Z,
    pellet_density: float = PELLET_DENSITY_KG_M3,
    air_density: float = AIR_DENSITY_KG_M3,
    water_density: float = WATER_DENSITY_KG_M3,
    air_drag_cd: float = AIR_DRAG_COEFF,
    water_drag_cd: float = WATER_DRAG_COEFF,
    water_spin_damp: float = WATER_SPIN_DAMPING,
    gravity: float = GRAVITY_M_S2,
) -> tuple[list[Vector], list[Vector]]:
    """Numerically integrate particle trajectory considering air drag, water drag, and buoyancy."""
    cylinder_height = (radius_m * 2.0) * aspect_ratio
    volume = math.pi * (radius_m ** 2) * cylinder_height
    mass = pellet_density * volume
    area = math.pi * (radius_m ** 2)

    pos = start_pos.copy()
    vel = start_vel.copy()
    spin = start_spin.copy()
    rot = initial_rot.copy()

    positions = [pos.copy()]
    rotations = [rot.copy()]

    t = 0.0
    while t < duration_s:
        in_water = pos.z <= water_level_z
        rho = water_density if in_water else air_density
        cd = water_drag_cd if in_water else air_drag_cd

        if in_water:
            g_eff = gravity * (1.0 - water_density / pellet_density)
            acc_g = Vector((0.0, 0.0, -g_eff))
            spin_damp = water_spin_damp
        else:
            acc_g = Vector((0.0, 0.0, -gravity))
            spin_damp = 0.1

        speed = vel.length
        if speed > 1e-6:
            drag_mag = 0.5 * rho * cd * area * (speed ** 2)
            acc_drag = - (drag_mag / mass) * (vel / speed)
        else:
            acc_drag = Vector((0.0, 0.0, 0.0))

        acc = acc_g + acc_drag
        vel += acc * dt_s
        pos += vel * dt_s
        spin -= spin * spin_damp * dt_s
        rot += spin * dt_s
        t += dt_s

        positions.append(pos.copy())
        rotations.append(rot.copy())

    return positions, rotations


def add_particle_animation(
    obj: bpy.types.Object,
    emit_frame: float,
    end_frame: float,
    fps: float,
    position: Vector,
    velocity: Vector,
    spin: Vector,
    radius_m: float = PELLET_RADIUS_MEAN_M,
    aspect_ratio: float = PELLET_ASPECT_RATIO,
    water_level_z: float = WATER_LEVEL_Z,
    lifetime_s: float = PARTICLE_LIFETIME_S,
    pellet_density: float = PELLET_DENSITY_KG_M3,
    air_density: float = AIR_DENSITY_KG_M3,
    water_density: float = WATER_DENSITY_KG_M3,
    air_drag_cd: float = AIR_DRAG_COEFF,
    water_drag_cd: float = WATER_DRAG_COEFF,
    water_spin_damp: float = WATER_SPIN_DAMPING,
    gravity: float = GRAVITY_M_S2,
) -> None:
    death_frame = min(end_frame + 1.0, emit_frame + lifetime_s * fps)
    preferences = bpy.context.preferences.edit
    previous_interpolation = preferences.keyframe_new_interpolation_type

    preferences.keyframe_new_interpolation_type = "CONSTANT"
    for property_name in ("hide_viewport", "hide_render"):
        visibility_driver = obj.driver_add(property_name).driver
        visibility_driver.type = "SCRIPTED"
        visibility_driver.expression = (
            f"frame < {emit_frame:.8f} or frame > {death_frame:.8f}"
        )

    duration_s = max(0.1, (death_frame - emit_frame) / fps)
    dt_s = 0.005
    initial_rotation = Vector(obj.rotation_euler)
    positions, rotations = compute_particle_trajectory(
        position, velocity, spin, initial_rotation, duration_s,
        radius_m=radius_m, aspect_ratio=aspect_ratio, dt_s=dt_s, water_level_z=water_level_z,
        pellet_density=pellet_density, air_density=air_density, water_density=water_density,
        air_drag_cd=air_drag_cd, water_drag_cd=water_drag_cd, water_spin_damp=water_spin_damp,
        gravity=gravity,
    )

    sample_frames = [emit_frame]
    next_frame = math.ceil(emit_frame + 2.0)
    while next_frame < death_frame:
        sample_frames.append(float(next_frame))
        next_frame += 2
    sample_frames.append(death_frame)

    preferences.keyframe_new_interpolation_type = "LINEAR"
    max_idx = len(positions) - 1
    for frame in sample_frames:
        age = max(0.0, (frame - emit_frame) / fps)
        idx = min(max_idx, max(0, int(round(age / dt_s))))

        obj.location = positions[idx]
        obj.rotation_euler = rotations[idx]

        obj.keyframe_insert("location", frame=frame, group="Physical path (Air+Water Drag)")
        obj.keyframe_insert("rotation_euler", frame=frame, group="Pellet spin")

    set_interpolation(obj)
    preferences.keyframe_new_interpolation_type = previous_interpolation


def run_feed_animation(config: dict | None = None) -> None:
    """Execute feed spreader and particle animation with specified config."""
    cfg = config or {}
    spreader_move_path = cfg.get("spreader_move_obj", DEFAULT_SPREADER_MOVE_PATH)
    spreader_still_path = cfg.get("spreader_still_obj", DEFAULT_SPREADER_STILL_PATH)
    rpm = float(cfg.get("rpm", RPM))
    mass_flow_kg_min = float(cfg.get("mass_flow_kg_min", MASS_FLOW_KG_MIN))
    visual_particle_mass_kg = float(cfg.get("visual_particle_mass_kg", VISUAL_PARTICLE_MASS_KG))
    radius_mean = float(cfg.get("pellet_radius_mean_m", PELLET_RADIUS_MEAN_M))
    radius_std = float(cfg.get("pellet_radius_std_m", PELLET_RADIUS_STD_M))
    aspect_ratio = float(cfg.get("pellet_aspect_ratio", PELLET_ASPECT_RATIO))
    outward_speed = float(cfg.get("outward_speed_m_s", OUTWARD_SPEED_M_S))
    downward_speed = float(cfg.get("downward_speed_m_s", DOWNWARD_SPEED_M_S))
    seed = int(cfg.get("random_seed", RANDOM_SEED))
    water_level_z = float(cfg.get("water_level_z", WATER_LEVEL_Z))
    pellet_density = float(cfg.get("pellet_density_kg_m3", PELLET_DENSITY_KG_M3))
    air_density = float(cfg.get("air_density_kg_m3", AIR_DENSITY_KG_M3))
    water_density = float(cfg.get("water_density_kg_m3", WATER_DENSITY_KG_M3))
    air_drag_cd = float(cfg.get("air_drag_coeff", AIR_DRAG_COEFF))
    water_drag_cd = float(cfg.get("water_drag_coeff", WATER_DRAG_COEFF))
    water_spin_damp = float(cfg.get("water_spin_damping", WATER_SPIN_DAMPING))
    particle_lifetime_s = float(cfg.get("particle_lifetime_s", PARTICLE_LIFETIME_S))
    gravity = float(cfg.get("gravity_m_s2", GRAVITY_M_S2))

    particle_rate = mass_flow_kg_min / 60.0 / visual_particle_mass_kg

    if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    frame_start = float(scene.frame_start)
    frame_end = float(scene.frame_end)
    angular_speed = rpm * 2.0 * math.pi / 60.0

    rotor = bpy.data.objects.get("Feed_Rotor_30RPM")
    if rotor is None:
        spreader_move = find_or_import_spreader_move_object(spreader_move_path, spreader_still_path)
        tip = find_spreader_outlet_tip(spreader_move)

        system_collection = bpy.data.collections.get("Feed_Animation_30RPM_30kgmin")
        if system_collection is None:
            system_collection = bpy.data.collections.new("Feed_Animation_30RPM_30kgmin")
            scene.collection.children.link(system_collection)

        rotor = bpy.data.objects.new("Feed_Rotor_30RPM", None)
        rotor.empty_display_type = "ARROWS"
        rotor.empty_display_size = 0.12
        rotor.show_in_front = True
        system_collection.objects.link(rotor)

        spreader_world = spreader_move.matrix_world.copy()
        spreader_move.parent = rotor
        spreader_move.matrix_world = spreader_world

        outlet = bpy.data.objects.new("FishFeed_Outlet_30kgmin", None)
        outlet.empty_display_type = "CIRCLE"
        outlet.empty_display_size = 0.035
        outlet.show_in_front = True
        outlet.location = tip
        outlet.rotation_euler.y = math.pi / 2.0
        outlet.parent = rotor
        system_collection.objects.link(outlet)
        outlet["mass_flow_kg_min"] = mass_flow_kg_min
        outlet["visual_particle_mass_kg"] = visual_particle_mass_kg
        outlet["particle_rate_per_second"] = particle_rate
    else:
        system_collection = bpy.data.collections.get("Feed_Animation_30RPM_30kgmin")
        outlet = bpy.data.objects.get("FishFeed_Outlet_30kgmin")
        if system_collection is None or outlet is None:
            raise RuntimeError("The existing feed setup is incomplete")
        tip = outlet.location.copy()

    rotor["rotation_rpm"] = rpm
    rotor["angular_speed_rad_s"] = angular_speed
    rotor.rotation_mode = "XYZ"
    rotation_driver = rotor.driver_add("rotation_euler", 2).driver
    rotation_driver.type = "SCRIPTED"
    rotation_driver.expression = f"(frame-{frame_start:.8f})*{angular_speed / fps:.12f}"

    old_particle_collection = bpy.data.collections.get("FishFeed_Proxy_Particles")
    if old_particle_collection is not None:
        for old_particle in list(old_particle_collection.objects):
            bpy.data.objects.remove(old_particle, do_unlink=True)
        bpy.data.collections.remove(old_particle_collection)
    old_particle_mesh = bpy.data.meshes.get("FishFeed_Pellet_Mesh")
    if old_particle_mesh is not None and old_particle_mesh.users == 0:
        bpy.data.meshes.remove(old_particle_mesh)

    particle_collection = bpy.data.collections.new("FishFeed_Proxy_Particles")
    system_collection.children.link(particle_collection)
    particle_mesh = make_pellet_mesh(radius_mean, aspect_ratio)

    duration_s = max(0.0, (frame_end - frame_start) / fps)
    particle_count = int(math.floor(duration_s * particle_rate)) + 1
    rng = random.Random(seed)

    for index in range(particle_count):
        emit_time = index / particle_rate
        emit_frame = frame_start + emit_time * fps
        angle = angular_speed * emit_time
        cosine = math.cos(angle)
        sine = math.sin(angle)

        position = Vector(
            (
                cosine * tip.x - sine * tip.y,
                sine * tip.x + cosine * tip.y,
                tip.z,
            )
        )
        radius = max(1.0e-6, math.hypot(position.x, position.y))
        radial = Vector((position.x / radius, position.y / radius, 0.0))
        tangent = Vector((-position.y / radius, position.x / radius, 0.0))

        position += tangent * rng.uniform(-0.014, 0.014)
        position.z += rng.uniform(-0.014, 0.014)
        velocity = (
            tangent * (angular_speed * radius + rng.uniform(-0.16, 0.16))
            + radial * (outward_speed + rng.uniform(-0.12, 0.18))
            + Vector(
                (
                    rng.uniform(-0.08, 0.08),
                    rng.uniform(-0.08, 0.08),
                    -downward_speed + rng.uniform(-0.16, 0.10),
                )
            )
        )

        raw_radius = rng.gauss(radius_mean, radius_std)
        min_r = max(0.001, radius_mean - 3.0 * radius_std)
        max_r = radius_mean + 3.0 * radius_std
        radius_i = max(min_r, min(max_r, raw_radius))

        particle = bpy.data.objects.new(f"FeedPellet_{index + 1:04d}", particle_mesh)
        particle_collection.objects.link(particle)
        particle.rotation_mode = "XYZ"
        particle.rotation_euler = (
            rng.uniform(0.0, math.tau),
            rng.uniform(0.0, math.tau),
            rng.uniform(0.0, math.tau),
        )
        scale_ratio = radius_i / radius_mean
        particle.scale = (scale_ratio, scale_ratio, scale_ratio)
        particle["pellet_radius_m"] = radius_i
        particle["pellet_radius_mean_m"] = radius_mean
        particle["pellet_radius_std_m"] = radius_std
        particle["proxy_mass_kg"] = visual_particle_mass_kg
        particle["emission_time_s"] = emit_time
        spin = Vector(
            (
                rng.uniform(-7.0, 7.0),
                rng.uniform(-7.0, 7.0),
                rng.uniform(-7.0, 7.0),
            )
        )
        add_particle_animation(
            particle,
            emit_frame,
            frame_end,
            fps,
            position,
            velocity,
            spin,
            radius_m=radius_i,
            aspect_ratio=aspect_ratio,
            water_level_z=water_level_z,
            lifetime_s=particle_lifetime_s,
            pellet_density=pellet_density,
            air_density=air_density,
            water_density=water_density,
            air_drag_cd=air_drag_cd,
            water_drag_cd=water_drag_cd,
            water_spin_damp=water_spin_damp,
            gravity=gravity,
        )

    scene["feed_rotation_rpm"] = rpm
    scene["feed_mass_flow_kg_min"] = mass_flow_kg_min
    scene["feed_particle_rate_s"] = particle_rate
    scene["feed_particle_count"] = particle_count

    print(
        "FEED_ANIMATION_DONE",
        "RPM", rpm,
        "KG_MIN", mass_flow_kg_min,
        "COUNT", particle_count,
        "OUTLET", tuple(round(v, 5) for v in tip),
    )
