"""Contained, deterministic schooling, independent of the cage motion source."""
import math
import random
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


def run_fish_schooling(config: dict | None = None) -> None:
    """Execute fish schooling simulation with the given configuration dictionary."""
    import bpy
    from mathutils import Vector
    from sim2blender.blender.enclosure import Enclosure, boundary_caps, stitch_membrane_seams
    from sim2blender.blender.fish.salmon import salmon_mesh

    cfg = config or {}
    count = int(cfg.get("fish_count", 1000))
    mean_length = float(cfg.get("fish_length_mean_m", 0.775))
    std_length = float(cfg.get("fish_length_std_m", 0.05))
    speed_bl = float(cfg.get("swim_speed_bl_s", 0.85))
    seed = int(cfg.get("random_seed", 7))
    cohesion_weight = float(cfg.get("cohesion_weight", 0.08))
    vert_osc = float(cfg.get("vertical_oscillation_m", 0.35))
    flow_dir = float(cfg.get("flow_direction", 1.0))
    wall_buffer = float(cfg.get("wall_buffer_m", 0.05))
    species_name = str(cfg.get("species", "Atlantic salmon"))

    if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    frame_start = scene.frame_start
    frame_end = scene.frame_end

    old_school = bpy.data.collections.get("Fish school")
    if old_school is not None:
        for old_obj in list(old_school.objects):
            bpy.data.objects.remove(old_obj, do_unlink=True)
        bpy.data.collections.remove(old_school)

    cage_obj = bpy.data.objects.get("Membrane cage")
    if cage_obj is None:
        for o in bpy.data.objects:
            if o.type == "MESH" and ("membrane" in o.name.lower() or "cage" in o.name.lower()):
                cage_obj = o
                break

    if cage_obj is None:
        raise RuntimeError("No cage mesh object found in scene for fish schooling.")

    mesh = cage_obj.data
    matrix = cage_obj.matrix_world
    points = [matrix @ v.co for v in mesh.vertices]
    faces = [tuple(p.vertices) for p in mesh.polygons]
    faces_stitched = stitch_membrane_seams(faces, points)
    try:
        caps = boundary_caps(faces_stitched, points, allow_caps=True)
    except Exception:
        caps = []
    enclosure = Enclosure(points, faces_stitched + caps)
    cage_center = (enclosure.low + enclosure.high) * 0.5

    rng = random.Random(seed)
    school_collection = bpy.data.collections.new("Fish school")
    scene.collection.children.link(school_collection)

    template_mesh = salmon_mesh(mean_length)
    base_clearance = max(v.co.length for v in template_mesh.vertices) + mean_length * 1e-5 + wall_buffer

    fish_objects = []
    positions = []
    velocities = []
    fish_cruise_speeds = []
    fish_clearances = []

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

    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        elapsed_s = (frame - frame_start) / fps

        for i, fish_obj in enumerate(fish_objects):
            p = positions[i]
            v = velocities[i]
            clearance_i = fish_clearances[i]

            radial = p - cage_center
            tangent_x = -radial.y * flow_dir
            tangent_y = radial.x * flow_dir
            cruise_dir = Vector((tangent_x, tangent_y, math.sin(elapsed_s * 0.9 + i) * vert_osc))
            cruise_dir += (cage_center - p) * cohesion_weight
            if cruise_dir.length < 1e-8:
                cruise_dir = Vector((1.0, 0.0, 0.0))
            cruise_dir.normalize()

            current_speed = fish_cruise_speeds[i]
            direction = (v * 0.82 + cruise_dir * 0.18).normalized()
            step_length = current_speed / fps if frame > frame_start else 0.0

            target_p = p + direction * step_length
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
            print(f"Validated {count} fish at frame {frame}/{frame_end}", flush=True)

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



