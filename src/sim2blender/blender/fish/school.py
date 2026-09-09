"""Contained, deterministic schooling, independent of the cage motion source."""
import math
import random
from sim2blender.blender.enclosure import Enclosure

def add_fish_school(cage, faces, fish_count=1000, frames=120, fish_length=.6, speed=.6, seed=7, advect=False, fish_asset=None, fish_object=None, species='generic'):
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
    scene['fish_species'] = species
    return fish


