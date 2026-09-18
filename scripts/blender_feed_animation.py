"""Build a 30 RPM rotating feed arm and a 30 kg/min visual feed stream.

This script targets the 'spreader_move' object in the Blender scene, parents it to
a Z-axis rotor (30 RPM), and bakes ballistic fish-feed proxy particles (30 kg/min)
as self-contained keyframed animations in the saved .blend file.

Can be run directly from Blender GUI Scripting workspace OR via Terminal command:
    blender scene.blend --python scripts/blender_feed_animation.py
"""

from __future__ import annotations

import math
import os
import random

import bmesh
import bpy
from mathutils import Vector


# -----------------------------------------------------------------------------
# 投料系统物理与视觉参数配置 (Feed Simulation Configuration)
# -----------------------------------------------------------------------------
RPM = -30.0                   # 旋转臂转速 (RPM, 负值表示绕 Z 轴顺时针旋转，正值表示逆时针)
MASS_FLOW_KG_MIN = 30.0       # 饲料总质量流量 (kg/min)
VISUAL_PARTICLE_MASS_KG = 0.01# 每个视觉代理饲料颗粒代表的实际质量 (kg, 0.01 kg = 10g)
PARTICLE_RATE = (             # 每秒生成的视觉颗粒数量 (根据流量和单颗粒质量自动计算)
    MASS_FLOW_KG_MIN / 60.0 / VISUAL_PARTICLE_MASS_KG
)
PARTICLE_LIFETIME_S = 30.0    # 饲料颗粒存活时间 (秒) -> 超过该时间颗粒自动隐藏

# 饲料颗粒几何形状与大小正态分布控制 (Cylindrical Pellet & Normal Distribution N(μ, σ²))
PELLET_RADIUS_MEAN_M = 0.005  # 饲料颗粒截面半径均值 (米, μ = 5mm, 直径 10mm)
PELLET_RADIUS_STD_M = 0.0008  # 饲料颗粒截面半径标准差 (米, σ = 0.8mm)
PELLET_ASPECT_RATIO = 1.6     # 饲料小圆柱长径比 (高度 / 直径, 膨化颗粒典型值为 1.2 ~ 1.8)
PELLET_RADIUS_M = PELLET_RADIUS_MEAN_M  # 兼容性别名

OUTWARD_SPEED_M_S = 1.0       # 沿撒料臂向外的径向喷射速度 (m/s) -> 值越大抛洒越远
DOWNWARD_SPEED_M_S = 0.001      # 向下的初始垂直喷射速度 (m/s) -> 值越大下落越快
GRAVITY_M_S2 = 9.81           # 重力加速度 (m/s²)
RANDOM_SEED = 30030           # 随机种子 -> 保证每次生成的颗粒散射分布一致且可复现

# -----------------------------------------------------------------------------
# 空气 (Z > 0) 与水体 (Z <= 0) 双介质流体阻力与浮力配置
# -----------------------------------------------------------------------------
WATER_LEVEL_Z = 0.0           # 水面 Z 轴平面的高度 (米, Z > 0 为空气，Z <= 0 为水)
PELLET_DENSITY_KG_M3 = 1100.0 # 饲料颗粒密度 (kg/m³, 沉性饲料 ~1100 kg/m³，微重于水 1000 kg/m³)
AIR_DENSITY_KG_M3 = 1.225     # 空气密度 (kg/m³)
WATER_DENSITY_KG_M3 = 1000.0  # 水体密度 (kg/m³)
AIR_DRAG_COEFF = 0.47         # 空气阻力系数 Cd (球体/椭球体 ~0.47)
WATER_DRAG_COEFF = 0.85       # 水中阻力系数 Cd (水体流体粘滞阻力更强 ~0.85)
WATER_SPIN_DAMPING = 1.0      # 入水后自旋阻尼衰减率 (1/s, 入水后颗粒快速停止剧烈旋转)


def find_spreader_move_object() -> bpy.types.Object:
    """Find the rotating spreader object ('spreader_move') in the current scene."""
    obj = bpy.data.objects.get("spreader_move")
    if obj is not None:
        return obj

    # Fallback search for case-insensitive or partial match
    for o in bpy.data.objects:
        name_lower = o.name.lower()
        if "spreader" in name_lower and "move" in name_lower:
            return o

    available = [o.name for o in bpy.data.objects if "spreader" in o.name.lower()]
    hint = f" Found related objects: {available}" if available else ""
    raise RuntimeError(
        f"Could not find 'spreader_move' object in Blender scene.{hint}\n"
        "Please ensure the scene contains an object named 'spreader_move'."
    )


def find_spreader_outlet_tip(spreader_obj: bpy.types.Object) -> Vector:
    """Determine the outlet tip coordinates from the spreader_move geometry."""
    outlet_obj = bpy.data.objects.get("FishFeed_Outlet_30kgmin")
    if outlet_obj is not None:
        return outlet_obj.location.copy()

    if spreader_obj.type == "MESH" and spreader_obj.data.vertices:
        matrix = spreader_obj.matrix_world
        world_verts = [matrix @ v.co for v in spreader_obj.data.vertices]

        # Calculate radial distance from Z axis
        radii = [math.hypot(v.x, v.y) for v in world_verts]
        max_r = max(radii)

        # Average vertices within 5cm of the outermost radius (the nozzle tip)
        tip_verts = [v for v, r in zip(world_verts, radii) if r >= max_r - 0.05]
        if tip_verts:
            return sum(tip_verts, Vector()) / len(tip_verts)
        return sum(world_verts, Vector()) / len(world_verts)

    return spreader_obj.matrix_world.translation.copy()


def make_pellet_mesh() -> bpy.types.Mesh:
    """Create a realistic cylindrical feed pellet mesh."""
    mesh = bpy.data.meshes.new("FishFeed_Pellet_Mesh")
    bm = bmesh.new()
    # Height of the cylinder = diameter * aspect_ratio
    cylinder_height = (PELLET_RADIUS_MEAN_M * 2.0) * PELLET_ASPECT_RATIO
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=12,
        radius1=PELLET_RADIUS_MEAN_M,
        radius2=PELLET_RADIUS_MEAN_M,
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
    dt_s: float = 0.005,
) -> tuple[list[Vector], list[Vector]]:
    """Numerically integrate particle trajectory considering air drag, water drag, and buoyancy."""
    # Cylinder volume = pi * r^2 * h
    cylinder_height = (radius_m * 2.0) * PELLET_ASPECT_RATIO
    volume = math.pi * (radius_m ** 2) * cylinder_height
    mass = PELLET_DENSITY_KG_M3 * volume
    # Spherical projected drag area approximation: A = pi * r^2
    area = math.pi * (radius_m ** 2)

    pos = start_pos.copy()
    vel = start_vel.copy()
    spin = start_spin.copy()
    rot = initial_rot.copy()

    positions = [pos.copy()]
    rotations = [rot.copy()]

    t = 0.0
    while t < duration_s:
        in_water = pos.z <= WATER_LEVEL_Z
        rho = WATER_DENSITY_KG_M3 if in_water else AIR_DENSITY_KG_M3
        cd = WATER_DRAG_COEFF if in_water else AIR_DRAG_COEFF

        if in_water:
            # Net gravity minus buoyancy in water: g_eff = g * (1 - rho_water / rho_pellet)
            g_eff = GRAVITY_M_S2 * (1.0 - WATER_DENSITY_KG_M3 / PELLET_DENSITY_KG_M3)
            acc_g = Vector((0.0, 0.0, -g_eff))
            spin_damp = WATER_SPIN_DAMPING
        else:
            acc_g = Vector((0.0, 0.0, -GRAVITY_M_S2))
            spin_damp = 0.1

        # Quadratic Drag: F_drag = -0.5 * rho * Cd * A * |v| * v
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
) -> None:
    death_frame = min(end_frame + 1.0, emit_frame + PARTICLE_LIFETIME_S * fps)
    preferences = bpy.context.preferences.edit
    previous_interpolation = preferences.keyframe_new_interpolation_type

    preferences.keyframe_new_interpolation_type = "CONSTANT"
    for property_name in ("hide_viewport", "hide_render"):
        visibility_driver = obj.driver_add(property_name).driver
        visibility_driver.type = "SCRIPTED"
        visibility_driver.expression = (
            f"frame < {emit_frame:.8f} or frame > {death_frame:.8f}"
        )

    # Pre-simulate physical trajectory across Air (Z > WATER_LEVEL_Z) and Water (Z <= WATER_LEVEL_Z)
    duration_s = max(0.1, (death_frame - emit_frame) / fps)
    dt_s = 0.005
    initial_rotation = Vector(obj.rotation_euler)
    positions, rotations = compute_particle_trajectory(
        position, velocity, spin, initial_rotation, duration_s, radius_m=radius_m, dt_s=dt_s
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



def main() -> None:
    if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    frame_start = float(scene.frame_start)
    frame_end = float(scene.frame_end)
    angular_speed = RPM * 2.0 * math.pi / 60.0

    rotor = bpy.data.objects.get("Feed_Rotor_30RPM")
    if rotor is None:
        spreader_move = find_spreader_move_object()
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
        outlet["mass_flow_kg_min"] = MASS_FLOW_KG_MIN
        outlet["visual_particle_mass_kg"] = VISUAL_PARTICLE_MASS_KG
        outlet["particle_rate_per_second"] = PARTICLE_RATE
        outlet["description"] = "Each visible pellet represents 0.01 kg of feed"
    else:
        system_collection = bpy.data.collections.get("Feed_Animation_30RPM_30kgmin")
        outlet = bpy.data.objects.get("FishFeed_Outlet_30kgmin")
        if system_collection is None or outlet is None:
            raise RuntimeError("The existing feed setup is incomplete")
        tip = outlet.location.copy()

    rotor["rotation_rpm"] = RPM
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
    particle_mesh = make_pellet_mesh()

    duration_s = max(0.0, (frame_end - frame_start) / fps)
    particle_count = int(math.floor(duration_s * PARTICLE_RATE)) + 1
    rng = random.Random(RANDOM_SEED)

    for index in range(particle_count):
        emit_time = index / PARTICLE_RATE
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
            + radial * (OUTWARD_SPEED_M_S + rng.uniform(-0.12, 0.18))
            + Vector(
                (
                    rng.uniform(-0.08, 0.08),
                    rng.uniform(-0.08, 0.08),
                    -DOWNWARD_SPEED_M_S + rng.uniform(-0.16, 0.10),
                )
            )
        )

        # Sample particle radius from normal distribution N(μ, σ²)
        raw_radius = rng.gauss(PELLET_RADIUS_MEAN_M, PELLET_RADIUS_STD_M)
        min_r = max(0.001, PELLET_RADIUS_MEAN_M - 3.0 * PELLET_RADIUS_STD_M)
        max_r = PELLET_RADIUS_MEAN_M + 3.0 * PELLET_RADIUS_STD_M
        radius_i = max(min_r, min(max_r, raw_radius))

        particle = bpy.data.objects.new(f"FeedPellet_{index + 1:04d}", particle_mesh)
        particle_collection.objects.link(particle)
        particle.rotation_mode = "XYZ"
        particle.rotation_euler = (
            rng.uniform(0.0, math.tau),
            rng.uniform(0.0, math.tau),
            rng.uniform(0.0, math.tau),
        )
        scale_ratio = radius_i / PELLET_RADIUS_MEAN_M
        particle.scale = (scale_ratio, scale_ratio, scale_ratio)
        particle["pellet_radius_m"] = radius_i
        particle["pellet_radius_mean_m"] = PELLET_RADIUS_MEAN_M
        particle["pellet_radius_std_m"] = PELLET_RADIUS_STD_M
        particle["proxy_mass_kg"] = VISUAL_PARTICLE_MASS_KG
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
        )

    scene["feed_rotation_rpm"] = RPM
    scene["feed_mass_flow_kg_min"] = MASS_FLOW_KG_MIN
    scene["feed_particle_rate_s"] = PARTICLE_RATE
    scene["feed_particle_proxy_mass_kg"] = VISUAL_PARTICLE_MASS_KG
    scene["feed_particle_count"] = particle_count
    scene["feed_pellet_radius_mean_m"] = PELLET_RADIUS_MEAN_M
    scene["feed_pellet_radius_std_m"] = PELLET_RADIUS_STD_M
    scene["feed_outlet_world_frame1"] = tuple(tip)

    preview_frame = min(scene.frame_end, scene.frame_start + round(fps * 1.5))
    scene.frame_set(preview_frame)

    current_path = bpy.data.filepath
    folder = os.path.dirname(current_path) or os.getcwd()
    stem = os.path.splitext(os.path.basename(current_path))[0]
    if not stem.endswith("_feed_animation"):
        stem += "_feed_animation"
    save_path = os.path.join(folder, stem + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=save_path, check_existing=False)

    print(
        "FEED_ANIMATION_DONE",
        save_path,
        "RPM", RPM,
        "KG_MIN", MASS_FLOW_KG_MIN,
        "RATE_S", PARTICLE_RATE,
        "COUNT", particle_count,
        "OUTLET", tuple(round(value, 5) for value in tip),
    )


if __name__ == "__main__":
    main()
