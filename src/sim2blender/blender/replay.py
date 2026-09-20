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


def apply_aquasim_replay(
    results_path: str | Path,
    model_path: str | Path | None = None,
    wave_period: float = 5.0,
    frames_per_wave: int = 40,
    fps: int = 25,
) -> None:
    """Apply AquaSim node movement to Membrane cage and other model meshes."""
    import math
    from pathlib import Path
    import bpy
    from sim2blender.io.aquasim.model import read_model
    from sim2blender.io.aquasim.results import read_results, map_nodes
    from sim2blender.core.timeline import sample_frames, wave_timing

    results_p = Path(results_path).resolve()
    if not results_p.is_file():
        raise FileNotFoundError(f"AquaSim results file not found: {results_p}")

    results = read_results(results_p)
    scene = bpy.context.scene

    if model_path is None and "source_file" in scene:
        model_path = scene["source_file"]
    if model_path is None and "amodel_path" in scene:
        model_path = scene["amodel_path"]

    cage = bpy.data.objects.get("Membrane cage")
    if cage is None:
        for o in bpy.data.objects:
            if o.type == "MESH" and "membrane" in o.name.lower():
                cage = o
                break

    if cage is None:
        raise RuntimeError("No 'Membrane cage' object found in the scene to apply replay onto.")

    if model_path is None and "source_file" in cage:
        model_path = cage["source_file"]

    if not model_path or not Path(model_path).is_file():
        raise RuntimeError("Could not determine .amodel file path for node mapping.")

    model = read_model(model_path)
    mapping = map_nodes(model, results)

    step_sec = wave_timing(len(results.times), wave_period, frames_per_wave, fps)["step_seconds"]
    frames = sample_frames(len(results.times), step_sec, fps)

    scene.frame_start = 1
    scene.frame_end = math.ceil(frames[-1])
    scene.render.fps = fps
    scene.render.fps_base = 1

    for mod in list(cage.modifiers):
        if mod.type == "CLOTH":
            cage.modifiers.remove(mod)

    node_ids = None
    if "node_id" in cage.data.attributes:
        node_ids = [d.value for d in cage.data.attributes["node_id"].data]
    elif "model_node_ids" in cage:
        node_ids = list(cage["model_node_ids"])

    if not node_ids:
        raise RuntimeError("The cage mesh does not contain 'node_id' attribute or 'model_node_ids'.")

    if cage.data.shape_keys:
        for key in list(cage.data.shape_keys.key_blocks):
            cage.shape_key_remove(key)

    for step, positions in enumerate(results.positions):
        key = cage.shape_key_add(name=f"Time_{results.times[step]:.4f}")
        key.interpolation = "KEY_LINEAR"
        coords = [c for nid in node_ids for c in positions[mapping[nid]]]
        key.data.foreach_set("co", coords)

    keys = cage.data.shape_keys
    keys.use_relative = False

    for step, key in enumerate(keys.key_blocks):
        keys.eval_time = key.frame
        keys.keyframe_insert("eval_time", frame=frames[step])

    if keys.animation_data and keys.animation_data.action:
        action = keys.animation_data.action
        fcurves = getattr(action, "fcurves", [])
        for curve in fcurves:
            for pt in curve.keyframe_points:
                pt.interpolation = "LINEAR"

    scene["source_times"] = results.times
    scene["source_frames"] = frames
    scene["results_path"] = str(results_p)
    scene["wave_period_seconds"] = wave_period
    scene["structural_frames_per_wave"] = frames_per_wave
    scene["structural_step_seconds"] = step_sec

    print(
        "AQUASIM_REPLAY_DONE",
        f"Samples: {len(results.times)}",
        f"Frames: 1 -> {scene.frame_end}",
        f"FPS: {fps}",
    )

