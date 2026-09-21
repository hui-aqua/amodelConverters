"""Hydrodynamic wave and current environment model for Sim2Blender.

Calculates water surface elevation and 3D water velocity field (mean current + linear wave orbital motion)
and animates water surface mesh displacement via Shape Keys.
"""

from __future__ import annotations
import math
from typing import Sequence
import bpy
from mathutils import Vector
from sim2blender.core.waves import jonswap_components, spectral_elevation, wave_options


def calculate_water_velocity(
    pos: Vector,
    t: float,
    current_speed: float = 0.5,
    current_dir_deg: float = 0.0,
    wave_height: float = 1.0,
    wave_period: float = 5.0,
    wave_length: float = 30.0,
    wave_dir_deg: float = 0.0,
    water_level: float = 0.0,
    wave_type: str = "regular",
    jonswap_gamma: float = 3.3,
    wave_components: int = 64,
    wave_seed: int = 42,
    wave_spread_deg: float = 20.0,
) -> Vector:
    """Calculate 3D water velocity vector at position (x, y, z) and time t."""
    if pos.z > water_level:
        return Vector((0.0, 0.0, 0.0))

    # Mean current velocity vector
    curr_rad = math.radians(current_dir_deg)
    v_curr = Vector((
        current_speed * math.cos(curr_rad),
        current_speed * math.sin(curr_rad),
        0.0,
    ))

    if wave_height <= 0 or wave_period <= 0:
        return v_curr

    if wave_type == "jonswap":
        velocity = v_curr.copy()
        for a, omega, kx, ky, offset in jonswap_components(wave_height, wave_period, wave_dir_deg, jonswap_gamma, wave_components, wave_seed, wave_spread_deg):
            k = math.hypot(kx, ky)
            phase = kx*pos.x + ky*pos.y - omega*t + offset
            speed = a * omega * math.exp(k * min(0.0, pos.z-water_level))
            velocity += Vector((speed*kx/k*math.cos(phase), speed*ky/k*math.cos(phase), speed*math.sin(phase)))
        return velocity
    if wave_type != "regular":
        raise ValueError("Unknown wave model: " + wave_type)

    # Linear Airy wave orbital velocity kinematics
    wave_rad = math.radians(wave_dir_deg)
    k = (2.0 * math.pi) / max(wave_length, 0.1)
    omega = (2.0 * math.pi) / wave_period
    depth_z = min(0.0, pos.z - water_level)

    # Exponential decay factor exp(k * z) for deep water wave kinematics
    decay = math.exp(k * depth_z)
    phase = k * (pos.x * math.cos(wave_rad) + pos.y * math.sin(wave_rad)) - omega * t

    v_wave_horiz = (wave_height / 2.0) * omega * decay * math.cos(phase)
    v_wave_vert = (wave_height / 2.0) * omega * decay * math.sin(phase)

    v_wave = Vector((
        v_wave_horiz * math.cos(wave_rad),
        v_wave_horiz * math.sin(wave_rad),
        v_wave_vert,
    ))

    return v_curr + v_wave


def calculate_wave_elevation(
    x: float,
    y: float,
    t: float,
    wave_height: float = 1.0,
    wave_period: float = 5.0,
    wave_length: float = 30.0,
    wave_dir_deg: float = 0.0,
    water_level: float = 0.0,
    wave_type: str = "regular",
    jonswap_gamma: float = 3.3,
    wave_components: int = 64,
    wave_seed: int = 42,
    wave_spread_deg: float = 20.0,
) -> float:
    """Calculate wave surface height at (x, y) and time t."""
    if wave_type == "jonswap":
        return water_level + spectral_elevation(jonswap_components(wave_height, wave_period, wave_dir_deg, jonswap_gamma, wave_components, wave_seed, wave_spread_deg), x, y, t)
    if wave_type != "regular":
        raise ValueError("Unknown wave model: " + wave_type)
    if wave_height <= 0 or wave_period <= 0:
        return water_level
    wave_rad = math.radians(wave_dir_deg)
    k = (2.0 * math.pi) / max(wave_length, 0.1)
    omega = (2.0 * math.pi) / wave_period
    phase = k * (x * math.cos(wave_rad) + y * math.sin(wave_rad)) - omega * t
    return water_level + (wave_height / 2.0) * math.cos(phase)


def setup_cloth_hydrodynamic_forces(
    scene=None,
    current_speed: float = 0.5,
    current_dir_deg: float = 0.0,
    wave_height: float = 1.0,
    wave_period: float = 5.0,
    wave_dir_deg: float = 0.0,
    collection=None,
    current_drag_scale: float = 12.0,
    wave_force_scale: float = 8.0,
    wave_type: str = "regular",
    jonswap_gamma: float = 3.3,
    wave_components: int = 64,
    wave_seed: int = 42,
    wave_spread_deg: float = 20.0,
) -> dict:
    """Create or update Blender WIND force fields that act upon the cage cloth simulation.

    When native Blender cloth simulation is used (AquaSim replay is not selected),
    this generates physical hydrodynamic force fields so the net cage and mooring lines
    respond dynamically to the steady current flow and oscillating wave orbital surge.

    Args:
        scene: bpy.types.Scene (defaults to bpy.context.scene)
        current_speed: Current velocity in m/s
        current_dir_deg: Current flow direction in degrees (0 = +X, 90 = +Y)
        wave_height: Wave height (peak-to-trough) in meters
        wave_period: Wave period in seconds
        wave_dir_deg: Wave propagation direction in degrees
        collection: Target collection for force field empties (defaults to 'Water environment')
        current_drag_scale: Linear drag scaling multiplier for current WIND effector (default 12.0)
        wave_force_scale: Surge force scaling multiplier for wave orbital WIND effector (default 8.0)

    Returns:
        dict with created force objects and properties.
    """
    if scene is None:
        scene = bpy.context.scene

    if collection is None:
        collection = scene.collection.children.get("Water environment") or scene.collection

    # Remove existing hydrodynamic force effectors if already present
    for name in ("Hydrodynamic_Current_Force", "Hydrodynamic_Wave_Force"):
        existing = scene.objects.get(name)
        if existing:
            bpy.data.objects.remove(existing, do_unlink=True)

    # 1. Steady Current Force (WIND effector)
    rad_c = math.radians(current_dir_deg)
    dir_curr = Vector((math.cos(rad_c), math.sin(rad_c), 0.0))
    if dir_curr.length > 1e-6:
        dir_curr.normalize()
    else:
        dir_curr = Vector((1.0, 0.0, 0.0))

    bpy.ops.object.effector_add(type="WIND")
    curr_wind = bpy.context.object
    curr_wind.name = "Hydrodynamic_Current_Force"
    curr_wind.empty_display_size = 5.0
    curr_wind.rotation_euler = Vector((0, 0, 1)).rotation_difference(dir_curr).to_euler()
    # Net drag force scaling gives realistic displacement for flexible aquaculture nets
    curr_wind.field.strength = max(float(current_speed), 0.0) * float(current_drag_scale)

    if collection and curr_wind.name not in collection.objects:
        collection.objects.link(curr_wind)
    for col in list(curr_wind.users_collection):
        if col != collection:
            col.objects.unlink(curr_wind)

    # 2. Oscillatory Wave Force (WIND effector with scripted driver)
    rad_w = math.radians(wave_dir_deg)
    dir_wave = Vector((math.cos(rad_w), math.sin(rad_w), 0.0))
    if dir_wave.length > 1e-6:
        dir_wave.normalize()
    else:
        dir_wave = Vector((1.0, 0.0, 0.0))

    bpy.ops.object.effector_add(type="WIND")
    wave_wind = bpy.context.object
    wave_wind.name = "Hydrodynamic_Wave_Force"
    wave_wind.empty_display_size = 5.0
    wave_wind.rotation_euler = Vector((0, 0, 1)).rotation_difference(dir_wave).to_euler()

    # Dynamic wave driver
    fps = scene.render.fps / scene.render.fps_base if scene.render.fps_base else scene.render.fps
    fps = max(float(fps), 1.0)
    period = max(float(wave_period), 0.1)
    wave_amp = max(float(wave_height), 0.0) * float(wave_force_scale)

    if wave_type == "jonswap":
        components = jonswap_components(wave_height, wave_period, wave_dir_deg, jonswap_gamma, wave_components, wave_seed, wave_spread_deg)
        for frame in range(scene.frame_start, scene.frame_end + 1):
            t = (frame - scene.frame_start) / fps
            wave_wind.field.strength = 2 * wave_force_scale * spectral_elevation(components, 0, 0, t)
            wave_wind.field.keyframe_insert("strength", frame=frame)
    else:
        fcurve = wave_wind.field.driver_add("strength")
        driver = fcurve.driver
        driver.type = "SCRIPTED"
        driver.expression = f"{wave_amp:.4f} * cos(2.0 * 3.14159265 * (frame - {scene.frame_start}) / ({fps:.2f} * {period:.4f}))"

    if collection and wave_wind.name not in collection.objects:
        collection.objects.link(wave_wind)
    for col in list(wave_wind.users_collection):
        if col != collection:
            col.objects.unlink(wave_wind)

    return {
        "current_force_obj": curr_wind,
        "wave_force_obj": wave_wind,
        "current_strength": curr_wind.field.strength,
        "wave_amplitude": wave_amp,
    }


def set_wave_and_current(
    scene=None,
    current_speed: float = 0.5,
    current_dir_deg: float = 0.0,
    wave_height: float = 1.0,
    wave_period: float = 5.0,
    wave_length: float = 30.0,
    wave_dir_deg: float = 0.0,
    water_level: float = 0.0,
    animate_water_surface: bool = True,
    setup_cloth_forces: bool = True,
    current_drag_scale: float = 12.0,
    wave_force_scale: float = 8.0,
    wave_type: str = "regular",
    jonswap_gamma: float = 3.3,
    wave_components: int = 64,
    wave_seed: int = 42,
    wave_spread_deg: float = 20.0,
) -> dict:
    """Configure wave and current hydrodynamic parameters in Blender scene."""
    if scene is None:
        scene = bpy.context.scene

    if wave_type not in ("regular", "jonswap"):
        raise ValueError("Unknown wave model: " + wave_type)
    components = jonswap_components(wave_height, wave_period, wave_dir_deg, jonswap_gamma, wave_components, wave_seed, wave_spread_deg) if wave_type == "jonswap" else ()
    options = dict(wave_type=wave_type, jonswap_gamma=jonswap_gamma,
                   wave_components=wave_components, wave_seed=wave_seed, wave_spread_deg=wave_spread_deg)
    for name, value in options.items():
        scene[name] = value

    scene["current_speed_m_s"] = float(current_speed)
    scene["current_direction_deg"] = float(current_dir_deg)
    scene["wave_height_m"] = float(wave_height)
    scene["wave_period_s"] = float(wave_period)
    scene["wave_length_m"] = float(wave_length)
    scene["wave_direction_deg"] = float(wave_dir_deg)
    scene["water_level_m"] = float(water_level)
    scene["hydrodynamics_active"] = True

    # Setup physical force fields for cloth simulation under current and wave
    if setup_cloth_forces:
        setup_cloth_hydrodynamic_forces(
            scene=scene,
            current_speed=current_speed,
            current_dir_deg=current_dir_deg,
            wave_height=wave_height,
            wave_period=wave_period,
            wave_dir_deg=wave_dir_deg,
            current_drag_scale=current_drag_scale,
            wave_force_scale=wave_force_scale,
            **options,
        )

    # Animate water surface plane vertices via Shape Keys if present
    surf_obj = scene.objects.get("Water surface")
    if surf_obj and animate_water_surface:
        fps = scene.render.fps / scene.render.fps_base if scene.render.fps_base else scene.render.fps
        f_start = scene.frame_start
        f_end = scene.frame_end
        verts = surf_obj.data.vertices
        base_coords = [v.co.copy() for v in verts]

        # Rebuilding or selecting flat water must remove the previous wave animation.
        if surf_obj.data.shape_keys:
            surf_obj.shape_key_clear()
        if not surf_obj.data.shape_keys:
            surf_obj.shape_key_add(name="Basis", from_mix=False)

        if components:
            import numpy as np
            coordinates = np.array([tuple(p) for p in base_coords], dtype=np.float32)
            # Cache spatial phases; evaluate all vertices with NumPy per component.
            spatial = [(a, omega, kx*coordinates[:, 0] + ky*coordinates[:, 1] + offset)
                       for a, omega, kx, ky, offset in components]

        for frame in range(f_start, f_end + 1):
            t = (frame - f_start) / max(fps, 1.0)
            key = surf_obj.shape_key_add(name=f"Wave_{frame:04d}", from_mix=False)
            key.interpolation = "KEY_LINEAR"
            if components:
                wave_coords = coordinates.copy()
                wave_coords[:, 2] = water_level
                for a, omega, phase in spatial:
                    wave_coords[:, 2] += a * np.cos(phase - omega*t)
                key.data.foreach_set("co", wave_coords.ravel())
            else:
                wave_coords = []
                for p in base_coords:
                    eta = calculate_wave_elevation(
                        p.x, p.y, t, wave_height=wave_height, wave_period=wave_period,
                        wave_length=wave_length, wave_dir_deg=wave_dir_deg,
                        water_level=water_level,
                    )
                    wave_coords.extend((p.x, p.y, eta))
                key.data.foreach_set("co", wave_coords)

        keys = surf_obj.data.shape_keys
        keys.use_relative = False
        for step, key in enumerate(keys.key_blocks[1:], start=0):
            frame = f_start + step
            keys.eval_time = key.frame
            keys.keyframe_insert("eval_time", frame=frame)

        if keys.animation_data and keys.animation_data.action:
            action = keys.animation_data.action
            curves = getattr(action, "fcurves", [])
            for curve in curves:
                for pt in curve.keyframe_points:
                    pt.interpolation = "LINEAR"

    return {
        **options,
        "current_speed": current_speed,
        "current_dir_deg": current_dir_deg,
        "wave_height": wave_height,
        "wave_period": wave_period,
        "wave_length": wave_length,
        "wave_dir_deg": wave_dir_deg,
        "water_level": water_level,
    }


def get_hydrodynamic_parameters(scene=None) -> dict:
    """Retrieve hydrodynamic settings from scene metadata or return defaults."""
    if scene is None:
        scene = bpy.context.scene
    return {
        **wave_options(scene),
        "current_speed": float(scene.get("current_speed_m_s", 0.0)),
        "current_dir_deg": float(scene.get("current_direction_deg", 0.0)),
        "wave_height": float(scene.get("wave_height_m", 0.0)),
        "wave_period": float(scene.get("wave_period_s", 5.0)),
        "wave_length": float(scene.get("wave_length_m", 30.0)),
        "wave_dir_deg": float(scene.get("wave_direction_deg", 0.0)),
        "water_level": float(scene.get("water_level_m", 0.0)),
    }

