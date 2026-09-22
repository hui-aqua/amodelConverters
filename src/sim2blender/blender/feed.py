"""Feed spreader kinematics and dual-medium ballistic pellet dynamics.

Imports or locates the feed spreader arm and stationary base, sets up the
continuous rotation driver, and integrates air/water ballistic trajectories
considering aerodynamic drag, hydrodynamic drag, buoyancy, and damping.
"""

from __future__ import annotations

import math
from pathlib import Path
import random

import bmesh
import bpy
from mathutils import Vector

from sim2blender.core.paths import PROJECT_ROOT

DEFAULT_SPREADER_MOVE_PATH = str(PROJECT_ROOT / "assets/spreaders/default/spreader_move.obj")
DEFAULT_SPREADER_STILL_PATH = str(PROJECT_ROOT / "assets/spreaders/default/spreader_still.obj")

DEFAULT_FEED_CONFIG = {
    "rpm": -30.0,
    "mass_flow_kg_min": 30.0,
    "visual_particle_mass_kg": 0.01,
    "particle_lifetime_s": 30.0,
    "pellet_radius_mean_m": 0.005,
    "pellet_radius_std_m": 0.0008,
    "pellet_aspect_ratio": 1.6,
    "outward_speed_m_s": 1.0,
    "downward_speed_m_s": 0.001,
    "gravity_m_s2": 9.81,
    "random_seed": 30030,
    "water_level_z": 0.0,
    "spreader_z_offset": 0.52,
    "spreader_heave_rao": 0.5,
    "pellet_density_kg_m3": 1100.0,
    "air_density_kg_m3": 1.225,
    "water_density_kg_m3": 1000.0,
    "air_drag_coeff": 0.47,
    "water_drag_coeff": 0.85,
    "water_spin_damping": 1.0,
}

# Backward compatibility aliases
RPM = DEFAULT_FEED_CONFIG["rpm"]
MASS_FLOW_KG_MIN = DEFAULT_FEED_CONFIG["mass_flow_kg_min"]
VISUAL_PARTICLE_MASS_KG = DEFAULT_FEED_CONFIG["visual_particle_mass_kg"]
PARTICLE_LIFETIME_S = DEFAULT_FEED_CONFIG["particle_lifetime_s"]
PELLET_RADIUS_MEAN_M = DEFAULT_FEED_CONFIG["pellet_radius_mean_m"]
PELLET_RADIUS_STD_M = DEFAULT_FEED_CONFIG["pellet_radius_std_m"]
PELLET_ASPECT_RATIO = DEFAULT_FEED_CONFIG["pellet_aspect_ratio"]
OUTWARD_SPEED_M_S = DEFAULT_FEED_CONFIG["outward_speed_m_s"]
DOWNWARD_SPEED_M_S = DEFAULT_FEED_CONFIG["downward_speed_m_s"]
GRAVITY_M_S2 = DEFAULT_FEED_CONFIG["gravity_m_s2"]
RANDOM_SEED = DEFAULT_FEED_CONFIG["random_seed"]
WATER_LEVEL_Z = DEFAULT_FEED_CONFIG["water_level_z"]
SPREADER_Z_OFFSET = DEFAULT_FEED_CONFIG["spreader_z_offset"]
SPREADER_HEAVE_RAO = DEFAULT_FEED_CONFIG["spreader_heave_rao"]
PELLET_DENSITY_KG_M3 = DEFAULT_FEED_CONFIG["pellet_density_kg_m3"]
AIR_DENSITY_KG_M3 = DEFAULT_FEED_CONFIG["air_density_kg_m3"]
WATER_DENSITY_KG_M3 = DEFAULT_FEED_CONFIG["water_density_kg_m3"]
AIR_DRAG_COEFF = DEFAULT_FEED_CONFIG["air_drag_coeff"]
WATER_DRAG_COEFF = DEFAULT_FEED_CONFIG["water_drag_coeff"]
WATER_SPIN_DAMPING = DEFAULT_FEED_CONFIG["water_spin_damping"]


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
    z_offset: float = SPREADER_Z_OFFSET,
    water_level_z: float = WATER_LEVEL_Z,
) -> bpy.types.Object:
    """Find existing 'spreader_move' or import from obj paths, applying waterline Z offset."""
    total_z = float(water_level_z) + float(z_offset)
    obj = bpy.data.objects.get("spreader_move")
    if obj is not None:
        return obj

    for o in bpy.data.objects:
        name_lower = o.name.lower()
        if "spreader" in name_lower and "move" in name_lower:
            return o

    def _resolve_spreader(path_val: str | Path | None, default_path: str) -> Path:
        candidate = Path(path_val or default_path)
        if candidate.is_file():
            return candidate.resolve()
        if (PROJECT_ROOT / candidate).is_file():
            return (PROJECT_ROOT / candidate).resolve()
        spreaders_dir = PROJECT_ROOT / "assets" / "spreaders"
        if spreaders_dir.is_dir():
            for found in spreaders_dir.glob(f"**/{candidate.name}"):
                if found.is_file():
                    return found.resolve()
        def_p = Path(default_path)
        if def_p.is_file():
            return def_p.resolve()
        return candidate.resolve()

    still_p = _resolve_spreader(still_obj_path, DEFAULT_SPREADER_STILL_PATH)
    if still_p.is_file() and not bpy.data.objects.get("spreader_still"):
        imported_still = import_obj_file(still_p)
        for o in imported_still:
            if o.type == "MESH":
                o.name = "spreader_still"
                o.location.z = total_z

    move_p = _resolve_spreader(move_obj_path, DEFAULT_SPREADER_MOVE_PATH)
    if move_p.is_file():
        imported_move = import_obj_file(move_p)
        for o in imported_move:
            if o.type == "MESH":
                o.name = "spreader_move"
                o.location.z = total_z
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
        return outlet_obj.matrix_world.translation.copy()

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
    current_speed: float = 0.0,
    current_dir_deg: float = 0.0,
    wave_height: float = 0.0,
    wave_period: float = 5.0,
    wave_length: float = 30.0,
    wave_dir_deg: float = 0.0,
    spectrum_options: dict | None = None,
    start_time_s: float = 0.0,
) -> tuple[list[Vector], list[Vector]]:
    """Numerically integrate particle trajectory considering air drag, water drag, buoyancy, current and waves."""
    from sim2blender.blender.environment import calculate_water_velocity, calculate_wave_elevation

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
        t_global = start_time_s + t
        surface_elev = calculate_wave_elevation(
            pos.x, pos.y, t_global,
            wave_height=wave_height,
            wave_period=wave_period,
            wave_length=wave_length,
            wave_dir_deg=wave_dir_deg,
            water_level=water_level_z,
            **(spectrum_options or {}),
        )
        in_water = pos.z <= surface_elev
        rho = water_density if in_water else air_density
        cd = water_drag_cd if in_water else air_drag_cd

        if in_water:
            g_eff = gravity * (1.0 - water_density / pellet_density)
            acc_g = Vector((0.0, 0.0, -g_eff))
            spin_damp = water_spin_damp
            v_water = calculate_water_velocity(
                pos, t_global,
                current_speed=current_speed,
                current_dir_deg=current_dir_deg,
                wave_height=wave_height,
                wave_period=wave_period,
                wave_length=wave_length,
                wave_dir_deg=wave_dir_deg,
                water_level=water_level_z,
                **(spectrum_options or {}),
            )
            v_rel = vel - v_water
        else:
            acc_g = Vector((0.0, 0.0, -gravity))
            spin_damp = 0.1
            v_rel = vel.copy()

        speed_rel = v_rel.length
        if speed_rel > 1e-6:
            drag_mag = 0.5 * rho * cd * area * (speed_rel ** 2)
            acc_drag = - (drag_mag / mass) * (v_rel / speed_rel)
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
    current_speed: float = 0.0,
    current_dir_deg: float = 0.0,
    wave_height: float = 0.0,
    wave_period: float = 5.0,
    wave_length: float = 30.0,
    wave_dir_deg: float = 0.0,
    spectrum_options: dict | None = None,
    start_time_s: float = 0.0,
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
        current_speed=current_speed,
        current_dir_deg=current_dir_deg,
        wave_height=wave_height,
        wave_period=wave_period,
        wave_length=wave_length,
        wave_dir_deg=wave_dir_deg,
        start_time_s=start_time_s,
        spectrum_options=spectrum_options,
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
    water_level_z = float(cfg.get("water_level_z", cfg.get("water_level_m", WATER_LEVEL_Z)))
    spreader_z_offset = float(cfg.get("spreader_z_offset", SPREADER_Z_OFFSET))
    spreader_heave_rao = float(cfg.get("spreader_heave_rao", cfg.get("heave_rao", SPREADER_HEAVE_RAO)))
    total_z_offset = water_level_z + spreader_z_offset
    pellet_density = float(cfg.get("pellet_density_kg_m3", PELLET_DENSITY_KG_M3))
    air_density = float(cfg.get("air_density_kg_m3", AIR_DENSITY_KG_M3))
    water_density = float(cfg.get("water_density_kg_m3", WATER_DENSITY_KG_M3))
    air_drag_cd = float(cfg.get("air_drag_coeff", AIR_DRAG_COEFF))
    water_drag_cd = float(cfg.get("water_drag_coeff", WATER_DRAG_COEFF))
    water_spin_damp = float(cfg.get("water_spin_damping", WATER_SPIN_DAMPING))
    particle_lifetime_s = float(cfg.get("particle_lifetime_s", PARTICLE_LIFETIME_S))
    gravity = float(cfg.get("gravity_m_s2", GRAVITY_M_S2))

    scene = bpy.context.scene
    hydro_active = scene.get("hydrodynamics_active", True)
    # Resolve hydrodynamics from config, falling back to scene properties if hydrodynamics are active
    fallback_current = scene.get("current_speed_m_s", 0.0) if hydro_active else 0.0
    fallback_wave_h = scene.get("wave_height_m", 0.0) if hydro_active else 0.0
    current_speed = float(cfg.get("current_speed_m_s", cfg.get("current_speed", fallback_current)))
    current_dir_deg = float(cfg.get("current_direction_deg", cfg.get("current_dir_deg", scene.get("current_direction_deg", 0.0))))
    wave_height = float(cfg.get("wave_height_m", cfg.get("wave_height", fallback_wave_h)))
    wave_period = float(cfg.get("wave_period_s", cfg.get("wave_period", scene.get("wave_period_s", 5.0))))
    wave_length = float(cfg.get("wave_length_m", cfg.get("wave_length", scene.get("wave_length_m", 30.0))))
    from sim2blender.core.waves import wave_options
    from sim2blender.blender.environment import calculate_wave_elevation
    spectrum_options = wave_options({**wave_options(scene), **cfg}) if hydro_active else {}
    wave_dir_deg = float(cfg.get("wave_direction_deg", cfg.get("wave_dir_deg", scene.get("wave_direction_deg", 0.0))))

    particle_rate = mass_flow_kg_min / 60.0 / visual_particle_mass_kg

    if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    fps = scene.render.fps / scene.render.fps_base
    frame_start = float(scene.frame_start)
    frame_end = float(scene.frame_end)
    angular_speed = rpm * 2.0 * math.pi / 60.0

    rotor = bpy.data.objects.get("Feed_Rotor_30RPM")
    if rotor is None:
        spreader_move = find_or_import_spreader_move_object(
            spreader_move_path,
            spreader_still_path,
            z_offset=spreader_z_offset,
            water_level_z=water_level_z,
        )
        still_obj = bpy.data.objects.get("spreader_still")
        if still_obj is not None:
            if still_obj.parent is not None:
                still_obj.parent = None
            still_obj.location = (0.0, 0.0, total_z_offset)

        if spreader_move.parent is not None:
            spreader_move.parent = None
        spreader_move.location = (0.0, 0.0, total_z_offset)
        bpy.context.view_layer.update()

        tip = find_spreader_outlet_tip(spreader_move)

        system_collection = bpy.data.collections.get("Feed_Animation_30RPM_30kgmin")
        if system_collection is None:
            system_collection = bpy.data.collections.new("Feed_Animation_30RPM_30kgmin")
            scene.collection.children.link(system_collection)

        rotor = bpy.data.objects.new("Feed_Rotor_30RPM", None)
        rotor.empty_display_type = "ARROWS"
        rotor.empty_display_size = 0.12
        rotor.show_in_front = True
        rotor.location = (0.0, 0.0, total_z_offset)
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
        system_collection.objects.link(outlet)
        bpy.context.view_layer.update()

        outlet_world = outlet.matrix_world.copy()
        outlet.parent = rotor
        outlet.matrix_world = outlet_world
        bpy.context.view_layer.update()

        outlet["mass_flow_kg_min"] = mass_flow_kg_min
        outlet["visual_particle_mass_kg"] = visual_particle_mass_kg
        outlet["particle_rate_per_second"] = particle_rate
    else:
        system_collection = bpy.data.collections.get("Feed_Animation_30RPM_30kgmin")
        outlet = bpy.data.objects.get("FishFeed_Outlet_30kgmin")
        if system_collection is None or outlet is None:
            raise RuntimeError("The existing feed setup is incomplete")
        tip = outlet.matrix_world.translation.copy()

    rotor["rotation_rpm"] = rpm
    rotor["angular_speed_rad_s"] = angular_speed
    rotor["spreader_heave_rao"] = spreader_heave_rao
    rotor.rotation_mode = "XYZ"
    rotation_driver = rotor.driver_add("rotation_euler", 2).driver
    rotation_driver.type = "SCRIPTED"
    rotation_driver.expression = f"(frame-{frame_start:.8f})*{angular_speed / fps:.12f}"

    # Spreader heave motion keyframing according to local wave elevation (RAO = 0.5)
    still_obj = bpy.data.objects.get("spreader_still")
    if wave_height > 0.0 and spreader_heave_rao > 0.0:
        for f_idx in range(int(frame_start), int(frame_end) + 1):
            t_sec = f_idx / fps
            eta_val = calculate_wave_elevation(
                0.0, 0.0, t_sec,
                wave_height=wave_height,
                wave_period=wave_period,
                wave_length=wave_length,
                wave_dir_deg=wave_dir_deg,
                water_level=water_level_z,
                **(spectrum_options or {}),
            ) - water_level_z
            heave_z = total_z_offset + spreader_heave_rao * eta_val
            rotor.location = (0.0, 0.0, heave_z)
            rotor.keyframe_insert("location", frame=f_idx)
            if still_obj is not None:
                still_obj.location = (0.0, 0.0, heave_z)
                still_obj.keyframe_insert("location", frame=f_idx)
    else:
        rotor.location = (0.0, 0.0, total_z_offset)
        if still_obj is not None:
            still_obj.location = (0.0, 0.0, total_z_offset)

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
        emit_time_global = (frame_start / fps) + emit_time
        angle = angular_speed * emit_time
        cosine = math.cos(angle)
        sine = math.sin(angle)

        if wave_height > 0.0 and spreader_heave_rao > 0.0:
            eta_emit = calculate_wave_elevation(
                0.0, 0.0, emit_time_global,
                wave_height=wave_height,
                wave_period=wave_period,
                wave_length=wave_length,
                wave_dir_deg=wave_dir_deg,
                water_level=water_level_z,
                **(spectrum_options or {}),
            ) - water_level_z
            heave_offset_z = spreader_heave_rao * eta_emit

            dt_d = 0.001
            eta_plus = calculate_wave_elevation(
                0.0, 0.0, emit_time_global + dt_d,
                wave_height=wave_height,
                wave_period=wave_period,
                wave_length=wave_length,
                wave_dir_deg=wave_dir_deg,
                water_level=water_level_z,
                **(spectrum_options or {}),
            ) - water_level_z
            eta_minus = calculate_wave_elevation(
                0.0, 0.0, emit_time_global - dt_d,
                wave_height=wave_height,
                wave_period=wave_period,
                wave_length=wave_length,
                wave_dir_deg=wave_dir_deg,
                water_level=water_level_z,
                **(spectrum_options or {}),
            ) - water_level_z
            v_heave_z = spreader_heave_rao * (eta_plus - eta_minus) / (2.0 * dt_d)
        else:
            heave_offset_z = 0.0
            v_heave_z = 0.0

        position = Vector(
            (
                cosine * tip.x - sine * tip.y,
                sine * tip.x + cosine * tip.y,
                tip.z + heave_offset_z,
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
                    -downward_speed + rng.uniform(-0.16, 0.10) + v_heave_z,
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
            current_speed=current_speed,
            current_dir_deg=current_dir_deg,
            wave_height=wave_height,
            wave_period=wave_period,
            wave_length=wave_length,
            wave_dir_deg=wave_dir_deg,
            start_time_s=emit_time_global,
            spectrum_options=spectrum_options,
        )

    scene["feed_rotation_rpm"] = rpm
    scene["feed_mass_flow_kg_min"] = mass_flow_kg_min
    scene["feed_particle_rate_s"] = particle_rate
    scene["feed_particle_count"] = particle_count
    scene["feed_current_speed_m_s"] = current_speed
    scene["feed_wave_height_m"] = wave_height
    scene["feed_spreader_z_offset"] = spreader_z_offset
    scene["feed_spreader_heave_rao"] = spreader_heave_rao
    scene["feed_water_level_z"] = water_level_z

    print(
        "FEED_ANIMATION_DONE",
        "RPM", rpm,
        "KG_MIN", mass_flow_kg_min,
        "COUNT", particle_count,
        "CURRENT_SPEED", current_speed,
        "WAVE_HEIGHT", wave_height,
        "SPREADER_Z_OFFSET", spreader_z_offset,
        "SPREADER_HEAVE_RAO", spreader_heave_rao,
        "OUTLET", tuple(round(v, 5) for v in tip),
    )
