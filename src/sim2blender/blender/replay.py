"""Presentation helpers for result-driven animation."""


def track_enclosure(scene, cage):
    """Frame the animated net and carry the studio lights along with it."""
    from mathutils import Vector
    camera = scene.camera
    keys = cage.data.shape_keys.key_blocks

    def bounds(key):
        points = [v.co for v in key.data]
        low = Vector(tuple(min(p[a] for p in points) for a in range(3)))
        high = Vector(tuple(max(p[a] for p in points) for a in range(3)))
        return (low+high)*.5, max((high-low).length, 1)

    scene.frame_set(1)
    origin, original_size = bounds(keys[0])
    direction = (camera.location-origin).normalized()
    lights = [scene.objects[name] for name in ('Key softbox', 'Warm fill', 'Rim')]
    lighting = [(light, light.location-origin, light.data.energy, light.data.size) for light in lights]
    for step, key in enumerate(keys):
        frame = scene['source_frames'][step]
        center, size = bounds(key)
        scale = size / original_size
        camera.location = center + direction*size*1.5
        camera.keyframe_insert('location', frame=frame)
        camera.data.ortho_scale = size*1.1
        camera.data.keyframe_insert('ortho_scale', frame=frame)
        for light, offset, energy, extent in lighting:
            light.location = center + offset*scale
            light.keyframe_insert('location', frame=frame)
            light.data.energy = energy*scale*scale
            light.data.size = extent*scale
            light.data.keyframe_insert('energy', frame=frame)
            light.data.keyframe_insert('size', frame=frame)
    for datablock in [camera, camera.data, *lights, *(light.data for light in lights)]:
        for layer in datablock.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:
                            key.interpolation = 'LINEAR'
    scene['camera_tracking'] = 'Animated net bounds; camera and studio lights follow each recorded step'
    scene.frame_set(1)
