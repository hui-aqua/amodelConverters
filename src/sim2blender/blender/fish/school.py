"""Contained, deterministic schooling, independent of the cage motion source."""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import bpy

from sim2blender.blender.enclosure import Enclosure

def add_fish_school(cage, faces, fish_count=1000, frames=120, fish_length=.775, speed=.6, seed=7, advect=False, fish_asset=None, fish_object=None, species='Atlantic salmon'):
    """Bake deterministic schooling against evaluated cloth at every integer frame.

    A sphere encloses each fish, so orientation cannot violate wall clearance.
    Paths hold at integer samples (CONSTANT interpolation) to avoid unchecked
    subframe crossings. Re-run after changing cloth or school parameters.
    With advect=True, follow changes in enclosure bounds before swimming;
    containment is still tested against the full evaluated surface.
    """
    import bpy
    from mathutils import Vector
    if not isinstance(fish_count, int) or not isinstance(frames, int) or fish_count < 0 or frames < 1 or not math.isfinite(fish_length) or fish_length <= 0 or not math.isfinite(speed) or speed < 0:
        raise ValueError('Require count >= 0, frames >= 1, length > 0, speed >= 0')
    scene = bpy.context.scene
    rng = random.Random(seed)
    from sim2blender.blender.fish.assets import load_fish_template
    appearance = load_fish_template(fish_length, fish_asset, fish_object)
    radius = appearance.clearance_radius
    school = bpy.data.collections.new('Fish school')
    scene.collection.children.link(school)
    template = appearance.mesh
    fish = []
    for i in range(fish_count):
        obj = bpy.data.objects.new(f'Fish_{i+1:03}', template)
        school.objects.link(obj)
        obj.rotation_mode = 'QUATERNION'
        obj['fish_asset_custom'] = appearance.custom
        obj['fish_species'] = species
        obj['fish_length_m'] = fish_length
        if not appearance.custom:
            obj['fish_species'] = 'Atlantic salmon'
            obj['fish_weight_kg'] = template['nominal_weight_kg']
        fish.append(obj)
    positions = []
    velocities = []
    relocations = 0
    previous_bounds = None
    for frame in range(1, frames + 1):
        scene.frame_set(frame)
        evaluated = cage.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            volume = Enclosure([cage.matrix_world @ v.co for v in mesh.vertices], faces)
        finally:
            evaluated.to_mesh_clear()
        center = (volume.low + volume.high) * .5
        for i, obj in enumerate(fish):
            if frame == 1:
                positions.append(volume.sample(rng, radius))
                velocities.append(Vector((1,0,0)))
            p = positions[i]
            if advect and previous_bounds is not None:
                low, high = previous_bounds
                p = Vector(tuple(volume.low[a] + (p[a]-low[a]) *
                                 (volume.high[a]-volume.low[a]) / max(high[a]-low[a], 1e-8)
                                 for a in range(3)))
            if not volume.contains(p, radius):
                p = project_inside_enclosure(p, radius, volume, center)
                if not volume.contains(p, radius):
                    p = volume.sample(rng, radius)
                relocations += 1
            radial = p - center
            elapsed = (frame-1) / (scene.render.fps / scene.render.fps_base)
            desired = Vector((-radial.y, radial.x, math.sin(elapsed*.96+i)*.4))
            desired += (center-p)*.08
            if desired.length < 1e-8:
                desired = Vector((1,0,0))
            direction = (velocities[i]*.85 + desired.normalized()*.15).normalized()
            step = speed / (scene.render.fps / scene.render.fps_base) if frame > 1 else 0
            # Clearance for the full step prevents crossing thin walls or concavities.
            target = p + direction * step
            if volume.contains(p, radius + step) and volume.contains(target, radius):
                p = target
            else:
                direction = (center-p).normalized()
            positions[i], velocities[i] = p, direction
            assert volume.contains(p, radius), f'Fish {i} escaped at frame {frame}'
            obj.location = p
            obj.rotation_quaternion = direction.to_track_quat('X', 'Z')
            obj.keyframe_insert(data_path='location', frame=frame)
            obj.keyframe_insert(data_path='rotation_quaternion', frame=frame)
        previous_bounds = (volume.low.copy(), volume.high.copy())
        if frame == 1 or frame % 20 == 0:
            print(f'Validated {fish_count} fish at frame {frame}/{frames}', flush=True)
    for obj in fish:
        for layer in obj.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:
                            key.interpolation = 'CONSTANT'
    scene['fish_count'] = fish_count
    scene['fish_length'] = fish_length
    scene['fish_seed'] = seed
    scene['fish_speed'] = speed
    scene['fish_relocations'] = relocations
    scene['fish_clearance_radius'] = radius
    scene['fish_asset_source'] = appearance.source
    scene['fish_species'] = species if appearance.custom else 'Atlantic salmon'
    if not appearance.custom:
        scene['fish_weight_kg'] = template['nominal_weight_kg']
    return fish


DEFAULT_SCHOOL_CONFIG = {
    "fish_count": 1000,
    "fish_length_mean_m": 0.775,
    "fish_length_std_m": 0.05,
    "swim_speed_bl_s": 0.85,
    "random_seed": 7,
    # Boid dynamics
    "separation_weight": 0.35,
    "separation_radius_m": 1.2,
    "alignment_weight": 0.25,
    "neighbor_radius_m": 2.5,
    "school_cohesion_weight": 0.15,
    # Milling & Cage behavior
    "milling_weight": 0.45,
    "flow_direction": 1.0,  # 1.0 = CCW, -1.0 = CW
    "cage_cohesion_weight": 0.08,
    # Depth layer
    "preferred_depth_min_m": -12.0,
    "preferred_depth_max_m": -2.5,
    "depth_weight": 0.25,
    "vertical_oscillation_m": 0.35,
    # Boundary avoidance & Kinematics
    "wall_detection_dist_m": 1.5,
    "wall_avoidance_weight": 0.75,
    "wall_buffer_m": 0.05,
    "max_turn_rate_deg_s": 120.0,
    # Hydrodynamic coupling
    "current_speed_m_s": 0.0,
    "current_direction_deg": 0.0,
    "wave_height_m": 0.0,
    "wave_period_s": 5.0,
    "wave_length_m": 30.0,
    "wave_direction_deg": 0.0,
    "water_level_m": 0.0,
    "hydro_coupling": 0.35,
    "rheotaxis_weight": 0.15,
    "species": "Atlantic salmon",
}


def cleanup_existing_fish_school() -> None:
    """Clear previously generated 'Fish school' collection and all fish objects."""
    import bpy
    old_school = bpy.data.collections.get("Fish school")
    if old_school is not None:
        for old_obj in list(old_school.objects):
            bpy.data.objects.remove(old_obj, do_unlink=True)
        bpy.data.collections.remove(old_school)

    for obj in list(bpy.data.objects):
        if obj.name.startswith("Fish_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith("salmon") or mesh.name.startswith("Fish_"):
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def find_membrane_cage_object() -> bpy.types.Object:
    """Find the cage mesh object representing the fish containment boundary."""
    import bpy
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
        if o.type == "MESH" and ("membrane" in o.name.lower() or "cage" in o.name.lower()):
            return o

    raise RuntimeError("No cage mesh object found in scene for fish schooling.")


def build_enclosure_from_cage(cage_obj: bpy.types.Object) -> Enclosure:
    """Construct a 3D BVH Enclosure from the cage mesh geometry for boundary checking."""
    from sim2blender.blender.enclosure import Enclosure, boundary_caps, stitch_membrane_seams
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


class SpatialGrid3D:
    """Fast O(N) 3D spatial hashing for neighbor queries in Boids simulation."""
    def __init__(self, cell_size: float):
        self.cell_size = max(float(cell_size), 0.1)
        self.inv_cell = 1.0 / self.cell_size
        self.cells: dict[tuple[int, int, int], list[int]] = {}

    def clear(self) -> None:
        self.cells.clear()

    def insert(self, idx: int, pos) -> None:
        key = (
            int(math.floor(pos.x * self.inv_cell)),
            int(math.floor(pos.y * self.inv_cell)),
            int(math.floor(pos.z * self.inv_cell)),
        )
        if key not in self.cells:
            self.cells[key] = [idx]
        else:
            self.cells[key].append(idx)

    def get_neighbors(self, idx: int, pos, radius: float) -> list[int]:
        cx = int(math.floor(pos.x * self.inv_cell))
        cy = int(math.floor(pos.y * self.inv_cell))
        cz = int(math.floor(pos.z * self.inv_cell))
        cell_range = max(1, int(math.ceil(radius * self.inv_cell)))
        neighbors = []
        for dx in range(-cell_range, cell_range + 1):
            for dy in range(-cell_range, cell_range + 1):
                for dz in range(-cell_range, cell_range + 1):
                    bucket = self.cells.get((cx + dx, cy + dy, cz + dz))
                    if bucket:
                        neighbors.extend(bucket)
        return [j for j in neighbors if j != idx]


def limit_turn_angle(v_current, desired_dir, max_turn_rad: float):
    """Limit angular change between current velocity and desired direction to prevent sudden snapping."""
    from mathutils import Vector, Quaternion
    if v_current.length < 1e-6 or desired_dir.length < 1e-6:
        return desired_dir.normalized() if desired_dir.length > 1e-6 else Vector((1.0, 0.0, 0.0))
    v_norm = v_current.normalized()
    d_norm = desired_dir.normalized()
    dot = max(-1.0, min(1.0, v_norm.dot(d_norm)))
    angle = math.acos(dot)
    if angle <= max_turn_rad or max_turn_rad <= 0:
        return d_norm
    axis = v_norm.cross(d_norm)
    if axis.length < 1e-6:
        axis = Vector((0.0, 0.0, 1.0)).cross(v_norm)
        if axis.length < 1e-6:
            axis = Vector((1.0, 0.0, 0.0)).cross(v_norm)
    axis.normalize()
    rot = Quaternion(axis, max_turn_rad)
    return (rot @ v_norm).normalized()


def project_inside_enclosure(pos, clearance: float, enclosure: Enclosure, cage_center):
    """Smoothly project a position inside the enclosure along the inward wall normal without teleporting."""
    from mathutils import Vector
    if enclosure.contains(pos, clearance):
        return pos
    nearest = enclosure.bvh.find_nearest(pos)
    if nearest[0] is not None:
        hit_pos = nearest[0]
        inward = pos - hit_pos
        if inward.length < 1e-6:
            inward = cage_center - hit_pos
        if inward.length < 1e-6:
            inward = Vector((0.0, 0.0, 1.0))
        inward.normalize()
        projected = hit_pos + inward * (clearance + enclosure.epsilon * 4.0)
        if enclosure.contains(projected, clearance):
            return projected
        towards_center = (cage_center - pos).normalized()
        for step in (clearance * 0.5, clearance, clearance * 2.0):
            test_p = projected + towards_center * step
            if enclosure.contains(test_p, clearance):
                return test_p
    for factor in (0.1, 0.25, 0.5, 0.75):
        test_p = pos.lerp(cage_center, factor)
        if enclosure.contains(test_p, clearance):
            return test_p
    return pos


def run_fish_schooling(config: dict | None = None) -> None:
    """Execute high-performance biological Boids fish schooling simulation with strict constant population."""
    import bpy
    from mathutils import Vector
    from sim2blender.blender.fish.salmon import salmon_mesh

    cfg = dict(DEFAULT_SCHOOL_CONFIG)
    if config:
        cfg.update(config)

    count = int(cfg["fish_count"])
    mean_length = float(cfg["fish_length_mean_m"])
    std_length = float(cfg["fish_length_std_m"])
    speed_bl = float(cfg["swim_speed_bl_s"])
    seed = int(cfg["random_seed"])

    # Boid Flocking
    sep_weight = float(cfg["separation_weight"])
    sep_rad = float(cfg["separation_radius_m"])
    align_weight = float(cfg["alignment_weight"])
    neighbor_rad = float(cfg["neighbor_radius_m"])
    cohesion_weight = float(cfg["school_cohesion_weight"])

    # Milling & Cage Orbit
    milling_weight = float(cfg["milling_weight"])
    flow_dir = float(cfg["flow_direction"])
    cage_cohesion_weight = float(cfg.get("cage_cohesion_weight", cfg.get("cohesion_weight", 0.08)))

    # Depth Preferences
    depth_min = float(cfg["preferred_depth_min_m"])
    depth_max = float(cfg["preferred_depth_max_m"])
    depth_weight = float(cfg["depth_weight"])
    vert_osc = float(cfg["vertical_oscillation_m"])

    # Boundary & Kinematics
    wall_detect_dist = float(cfg["wall_detection_dist_m"])
    wall_avoidance_weight = float(cfg["wall_avoidance_weight"])
    wall_buffer = float(cfg["wall_buffer_m"])
    max_turn_deg_s = float(cfg["max_turn_rate_deg_s"])

    species_name = str(cfg["species"])

    if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    frame_start = scene.frame_start
    frame_end = scene.frame_end
    max_turn_rad_per_frame = math.radians(max_turn_deg_s) / fps if fps > 0 else math.pi

    # Hydrodynamics
    current_speed = float(cfg.get("current_speed_m_s", cfg.get("current_speed", scene.get("current_speed_m_s", 0.0))))
    current_dir_deg = float(cfg.get("current_direction_deg", cfg.get("current_dir_deg", scene.get("current_direction_deg", 0.0))))
    wave_height = float(cfg.get("wave_height_m", cfg.get("wave_height", scene.get("wave_height_m", 0.0))))
    wave_period = float(cfg.get("wave_period_s", cfg.get("wave_period", scene.get("wave_period_s", 5.0))))
    wave_length = float(cfg.get("wave_length_m", cfg.get("wave_length", scene.get("wave_length_m", 30.0))))
    wave_dir_deg = float(cfg.get("wave_direction_deg", cfg.get("wave_dir_deg", scene.get("wave_direction_deg", 0.0))))
    water_level = float(cfg.get("water_level_m", cfg.get("water_level", scene.get("water_level_z", 0.0))))
    hydro_coupling = float(cfg.get("hydro_coupling", 0.35))
    rheotaxis_weight = float(cfg.get("rheotaxis_weight", 0.15))

    # 1. Clean up previously generated fish to guarantee exact N fish
    cleanup_existing_fish_school()

    cage_obj = find_membrane_cage_object()
    enclosure = build_enclosure_from_cage(cage_obj)
    cage_center = (enclosure.low + enclosure.high) * 0.5

    rng = random.Random(seed)
    school_collection = bpy.data.collections.new("Fish school")
    scene.collection.children.link(school_collection)

    template_mesh = salmon_mesh(mean_length)
    base_clearance = max(v.co.length for v in template_mesh.vertices) + mean_length * 1e-5 + wall_buffer

    fish_objects: list[bpy.types.Object] = []
    positions: list[Vector] = []
    velocities: list[Vector] = []
    fish_cruise_speeds: list[float] = []
    fish_clearances: list[float] = []

    # 2. Strict Constant Population Initialization (Frame 1 only)
    for i in range(count):
        raw_length = rng.gauss(mean_length, std_length)
        min_length = max(0.1, mean_length - 3.0 * std_length)
        max_length = mean_length + 3.0 * std_length
        length_i = max(min_length, min(max_length, raw_length))

        cruise_speed_i = speed_bl * length_i
        clearance_i = base_clearance * (length_i / mean_length)

        fish_cruise_speeds.append(cruise_speed_i)
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

    # 3. Spatial Grid for O(N) Boids Neighbor Lookup
    grid = SpatialGrid3D(cell_size=max(neighbor_rad, sep_rad, 2.0))

    # 4. Deterministic Simulation Loop Across All Frames
    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        elapsed_s = (frame - frame_start) / fps if fps > 0 else 0.0

        # Insert all fish positions into spatial grid for this time step
        grid.clear()
        for idx, pos in enumerate(positions):
            grid.insert(idx, pos)

        for i, fish_obj in enumerate(fish_objects):
            p = positions[i]
            v = velocities[i]
            clearance_i = fish_clearances[i]

            # (A) Boids Flocking Forces
            f_sep = Vector((0.0, 0.0, 0.0))
            f_align = Vector((0.0, 0.0, 0.0))
            f_cohesion = Vector((0.0, 0.0, 0.0))
            align_count = 0
            cohesion_sum = Vector((0.0, 0.0, 0.0))

            neighbors = grid.get_neighbors(i, p, neighbor_rad)
            for j in neighbors:
                p_j = positions[j]
                v_j = velocities[j]
                offset = p - p_j
                dist = offset.length
                if dist < 1e-4:
                    continue
                # Separation: inverse distance squared repulsion
                if dist < sep_rad:
                    f_sep += (offset / (dist * dist))
                # Alignment & Cohesion within neighbor radius
                f_align += v_j
                cohesion_sum += p_j
                align_count += 1

            if f_sep.length > 1e-6:
                f_sep.normalize()
            if align_count > 0:
                avg_v = f_align / align_count
                if avg_v.length > 1e-6:
                    f_align = avg_v.normalized()
                avg_pos = cohesion_sum / align_count
                diff = avg_pos - p
                if diff.length > 1e-6:
                    f_cohesion = diff.normalized()

            # (B) Toroidal Milling Orbit
            radial = p - cage_center
            f_milling = Vector((-radial.y * flow_dir, radial.x * flow_dir, 0.0))
            if f_milling.length > 1e-6:
                f_milling.normalize()
            f_cage_center = cage_center - p
            if f_cage_center.length > 1e-6:
                f_cage_center.normalize()

            # (C) Depth Layering & Natural Undulation
            f_depth_z = 0.0
            if p.z > depth_max:
                f_depth_z = -1.0 * min(1.0, (p.z - depth_max) / 2.0)
            elif p.z < depth_min:
                f_depth_z = 1.0 * min(1.0, (depth_min - p.z) / 2.0)
            else:
                f_depth_z = math.sin(elapsed_s * 0.9 + i) * 0.5
            f_depth = Vector((0.0, 0.0, f_depth_z * vert_osc))

            # (D) Predictive Net Wall Avoidance Steering
            f_wall = Vector((0.0, 0.0, 0.0))
            nearest = enclosure.bvh.find_nearest(p)
            if nearest[0] is not None:
                wall_dist = nearest[3]
                if wall_dist < wall_detect_dist:
                    wall_norm = p - nearest[0]
                    if wall_norm.length < 1e-6:
                        wall_norm = cage_center - nearest[0]
                    if wall_norm.length > 1e-6:
                        wall_norm.normalize()
                        proximity = max(0.0, min(1.0, (wall_detect_dist - wall_dist) / max(wall_detect_dist - clearance_i, 0.1)))
                        f_wall = wall_norm * (proximity * proximity)

            # (E) Combine Steering Forces
            steering = (
                f_sep * sep_weight +
                f_align * align_weight +
                f_cohesion * cohesion_weight +
                f_milling * milling_weight +
                f_cage_center * cage_cohesion_weight +
                f_depth * depth_weight +
                f_wall * wall_avoidance_weight
            )
            if steering.length < 1e-6:
                steering = v if v.length > 1e-6 else Vector((1.0, 0.0, 0.0))
            desired_dir = steering.normalized()

            # (F) Angular Turn Rate Limiting
            limited_dir = limit_turn_angle(v, desired_dir, max_turn_rad_per_frame)

            # (G) Autonomous Swimming Step
            swim_speed = fish_cruise_speeds[i]
            swim_step = limited_dir * (swim_speed / fps if frame > frame_start else 0.0)

            # (H) Ambient Hydrodynamic Coupling (Wave & Current)
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
                # Rheotaxis alignment with current
                if v_water.length > 0.08 and rheotaxis_weight > 0.0:
                    into_current = -v_water.normalized()
                    limited_dir = (limited_dir * (1.0 - rheotaxis_weight) + into_current * rheotaxis_weight).normalized()
            else:
                water_step = Vector((0.0, 0.0, 0.0))

            total_step = swim_step + water_step
            step_length = total_step.length
            final_dir = total_step.normalized() if step_length > 1e-6 else limited_dir

            # (I) Boundary Safe Update (Zero Teleportation, Zero Birth/Death)
            target_p = p + total_step
            if enclosure.contains(p, clearance_i + step_length) and enclosure.contains(target_p, clearance_i):
                p = target_p
            else:
                # Continuous boundary projection
                p = project_inside_enclosure(target_p, clearance_i, enclosure, cage_center)
                final_dir = (p - positions[i]).normalized() if (p - positions[i]).length > 1e-6 else limited_dir

            positions[i] = p
            velocities[i] = final_dir

            fish_obj.location = p
            fish_obj.rotation_quaternion = final_dir.to_track_quat("X", "Z")
            fish_obj.keyframe_insert("location", frame=frame)
            fish_obj.keyframe_insert("rotation_quaternion", frame=frame)

        if frame == frame_start or frame % 20 == 0:
            print(f"Validated {count} fish at frame {frame}/{frame_end}", flush=True)

    # 5. Clean Animation F-Curves
    for fish_obj in fish_objects:
        if fish_obj.animation_data and fish_obj.animation_data.action:
            action = fish_obj.animation_data.action
            curves = getattr(action, "fcurves", [])
            for curve in curves:
                for keypoint in curve.keyframe_points:
                    keypoint.interpolation = "CONSTANT"

    scene["fish_count"] = count
    scene["fish_length_mean_m"] = mean_length
    scene["fish_length_std_m"] = std_length




