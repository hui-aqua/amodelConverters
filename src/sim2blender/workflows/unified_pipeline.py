"""Unified pipeline: AquaSim Model -> Blender Physics scene with modular optional stages.

Modular stages:
1. AquaSim results replay (replaces cloth baking with node displacements from results)
2. Simple fish schooling
3. Feed spreader animation (defaults to assets/spreaders/default/spreader_move.obj and spreader_still.obj)
4. Fish feeding interaction animation
5. Cinematic camera
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path
import random
import sys

from sim2blender.core.paths import PROJECT_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sim2blender.io.aquasim.model import DEFAULT_INPUT, read_model

from sim2blender.io.aquasim.results import read_results, map_nodes
from sim2blender.core.timeline import sample_frames, wave_timing
from sim2blender.blender.enclosure import Enclosure, boundary_caps, stitch_membrane_seams
from sim2blender.blender.scene import mesh_object, constrain_axes, setup_view
from sim2blender.blender.geometry import build_members, round_net
from sim2blender.blender.ropes import rigid_beams, build_rope_dynamics
from sim2blender.blender.shading import apply_visualization


def build_unified_scene(config: dict) -> None:
    import bpy

    model_raw = config.get("model") or config.get("model_path")
    if not model_raw:
        raise ValueError("Missing 'model' or 'model_path' in configuration.")
    output_raw = config.get("output") or config.get("output_blend")
    if not output_raw:
        raise ValueError("Missing 'output' or 'output_blend' in configuration.")
    model_path = Path(model_raw).resolve()
    output_path = Path(output_raw).resolve()
    membrane_ids = [int(i) for i in config.get("membrane_ids", [])]
    cap_openings = bool(config.get("cap_openings", True))
    pin_top = bool(config.get("pin_top", True))
    base_frames = int(config.get("frames", 120))

    env_cfg = config.get("environment") or config.get("water")
    use_env = bool(env_cfg.get("enabled", True)) if isinstance(env_cfg, dict) else (env_cfg is not False)

    replay_cfg = config.get("replay")
    use_replay = bool(replay_cfg and replay_cfg.get("enabled", False))

    schooling_cfg = config.get("fish_schooling")
    use_schooling = bool(schooling_cfg and schooling_cfg.get("enabled", False))

    feed_cfg = config.get("feed_animation")
    use_feed = bool(feed_cfg and feed_cfg.get("enabled", False))

    feeding_cfg = config.get("fish_feeding")
    use_feeding = bool(feeding_cfg and feeding_cfg.get("enabled", False))

    camera_cfg = config.get("cinematic_camera")
    use_camera = bool(camera_cfg and camera_cfg.get("enabled", False))


    # 1. Read AquaSim model and extract membrane geometry
    print(f"GUI_STAGE: Reading AquaSim model {model_path.name}…", flush=True)
    model = read_model(model_path)
    membrane = [
        c for c in model.cells
        if c["component_tag"] == "membrane" and (not membrane_ids or c["component_id"] in membrane_ids)
    ]
    if not membrane:
        raise ValueError("No active membrane elements selected for enclosure.")

    ids = sorted({n for c in membrane for n in c["nodes"]})
    index = {n: i for i, n in enumerate(ids)}
    nodes = [model.nodes[n] for n in ids]
    points = [n.point for n in nodes]
    faces = [tuple(index[n] for n in c["nodes"]) for c in membrane]
    faces = stitch_membrane_seams(faces, points)

    caps = []
    if use_schooling or not use_replay:
        caps = boundary_caps(faces, points, cap_openings)
        # Validate enclosure geometry
        Enclosure(points, faces + caps).sample(random.Random(7), 0.5)

    # Initialize Blender Scene
    scene = bpy.data.scenes.new("Sim2Blender Scene")
    bpy.context.window.scene = scene
    collection = bpy.data.collections.new("AModel cage")
    scene.collection.children.link(collection)

    cage = mesh_object("Membrane cage", points, [], faces, collection)
    cage["source_file"] = str(model_path)
    cage["virtual_cap_count"] = len(caps)
    cage["active"] = True

    material = bpy.data.materials.new("Net strands")
    material.diffuse_color = (0.12, 0.3, 0.28, 1.0)
    cage.data.materials.append(material)

    for name, values, domain in [
        ("node_id", ids, "POINT"),
        ("component_id", [c["component_id"] for c in membrane], "FACE"),
        ("element_id", [c["element_id"] for c in membrane], "FACE"),
    ]:
        attr = cage.data.attributes.new(name, "INT", domain)
        for datum, value in zip(attr.data, values):
            datum.value = value

    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"

    geometry_report = []

    # 2. Motion Source: AquaSim Results Replay OR Blender Cloth Physics Bake
    if use_replay:
        results_path = Path(replay_cfg["results"]).resolve()
        if not results_path.is_file():
            raise FileNotFoundError(f"Results file not found: {results_path}")

        fps = int(replay_cfg.get("fps", 25))
        wave_period = float(replay_cfg.get("wave_period", 5.0))
        frames_per_wave = int(replay_cfg.get("frames_per_wave", 40))

        print(f"GUI_STAGE: Replaying AquaSim structural motion from {results_path.name}…", flush=True)
        results = read_results(results_path)
        mapping = map_nodes(model, results)

        step_sec = wave_timing(len(results.times), wave_period, frames_per_wave, fps)["step_seconds"]
        replay_frames = sample_frames(len(results.times), step_sec, fps)

        scene.frame_start = 1
        scene.frame_end = math.ceil(replay_frames[-1])
        scene.render.fps = fps
        scene.render.fps_base = 1

        # Apply animated shape keys to Membrane cage
        for step, positions in enumerate(results.positions):
            key = cage.shape_key_add(name=f"Time_{results.times[step]:.4f}")
            key.interpolation = "KEY_LINEAR"
            coords = [c for nid in ids for c in positions[mapping[nid]]]
            key.data.foreach_set("co", coords)

        keys = cage.data.shape_keys
        keys.use_relative = False
        for step, key in enumerate(keys.key_blocks):
            keys.eval_time = key.frame
            keys.keyframe_insert("eval_time", frame=replay_frames[step])

        if keys.animation_data and keys.animation_data.action:
            action = keys.animation_data.action
            curves = getattr(action, "fcurves", [])
            for curve in curves:
                for pt in curve.keyframe_points:
                    pt.interpolation = "LINEAR"

        # Build passive members
        geometry_report += build_members(model, collection, tags=("beam",))
        rigid_beams(collection)

        scene["source_times"] = results.times
        scene["source_frames"] = replay_frames
        scene["results_path"] = str(results_path)
        scene["wave_period_seconds"] = wave_period
        scene["structural_frames_per_wave"] = frames_per_wave
        scene["structural_step_seconds"] = step_sec
    else:
        # Standard Blender cloth simulation baking
        scene.frame_start, scene.frame_end = 1, base_frames
        scene.render.fps = 24

        pins = cage.vertex_groups.new(name="Fixed nodes")
        fixed = [i for i, n in enumerate(nodes) if not any(n.translate)]
        if fixed:
            pins.add(fixed, 1, "REPLACE")

        beam_nodes = {n for c in model.cells if c["component_tag"] == "beam" for n in c["nodes"]}
        beam_pins = [i for i, n in enumerate(ids) if n in beam_nodes]
        if beam_pins:
            pins.add(beam_pins, 1, "REPLACE")

        if pin_top:
            top = max(p[2] for p in points)
            extra = [i for i, p in enumerate(points) if abs(p[2] - top) < 0.001]
            pins.add(extra, 1, "REPLACE")

        cloth = cage.modifiers.new("Cage cloth", "CLOTH")
        cloth.settings.quality = 8
        cloth.settings.mass = 0.1
        cloth.settings.tension_stiffness = 40
        cloth.settings.compression_stiffness = 40
        cloth.settings.shear_stiffness = 20
        cloth.settings.vertex_group_mass = pins.name
        cloth.settings.effector_weights.gravity = 0.03
        cloth.settings.air_damping = 5.0
        cloth.point_cache.frame_start = 1
        cloth.point_cache.frame_end = base_frames

        constrain_axes(cage, nodes)
        geometry_report += build_members(model, collection, tags=("beam",))
        rigid_beams(collection)

        for node in model.nodes.values():
            if all(node.translate):
                continue
            obj = bpy.data.objects.new(f"Constraint node {node.id}", None)
            collection.objects.link(obj)
            obj.location = node.point
            obj.empty_display_size = 0.15
            obj.lock_location = tuple(not v for v in node.translate)
            obj["node_id"] = node.id

        scene.frame_set(1)
        bpy.context.view_layer.objects.active = cage
        cage.select_set(True)

        # Setup ocean water & hydrodynamic forces BEFORE cloth baking if environment is enabled
        if use_env:
            print("GUI_STAGE: Setting up ocean water & hydrodynamic forces for cloth physics…", flush=True)
            from sim2blender.blender.water import add_water
            from sim2blender.blender.environment import set_wave_and_current

            env_dict = env_cfg if isinstance(env_cfg, dict) else {}
            level = float(env_dict.get("water_level_m", env_dict.get("level", 0.0)))
            depth = float(env_dict.get("water_depth_m", env_dict.get("depth", 100.0)))
            size = float(env_dict.get("water_size_m", env_dict.get("size", 300.0)))

            curr_speed = float(env_dict.get("current_speed_m_s", env_dict.get("current_speed", 0.15)))
            curr_dir = float(env_dict.get("current_direction_deg", env_dict.get("current_dir_deg", 0.0)))
            wave_h = float(env_dict.get("wave_height_m", env_dict.get("wave_height", 0.30)))
            wave_t = float(env_dict.get("wave_period_s", env_dict.get("wave_period", 6.0)))
            wave_l = float(env_dict.get("wave_length_m", env_dict.get("wave_length", 25.0)))
            wave_dir = float(env_dict.get("wave_direction_deg", env_dict.get("wave_dir_deg", 0.0)))

            water_kwargs = {
                "level": level,
                "depth": depth,
                "size": size,
                "enable_volume": bool(env_dict.get("enable_volume", True)),
            }
            for opt in ("surface_resolution", "ior", "roughness", "scatter_density", "absorption_density", "sun_energy", "sun_elevation_deg", "sun_rotation_deg"):
                if opt in env_dict:
                    water_kwargs[opt] = env_dict[opt]

            add_water(scene, collection=collection, **water_kwargs)

            set_wave_and_current(
                scene,
                current_speed=curr_speed,
                current_dir_deg=curr_dir,
                wave_height=wave_h,
                wave_period=wave_t,
                wave_length=wave_l,
                wave_dir_deg=wave_dir,
                water_level=level,
                animate_water_surface=True,
                setup_cloth_forces=True,
            )

        print(f"GUI_STAGE: Simulating cage cloth net ({len(faces)} faces)…", flush=True)
        with bpy.context.temp_override(point_cache=cloth.point_cache):
            bpy.ops.ptcache.bake(bake=True)

        ropes, rope_report = build_rope_dynamics(model, collection, cage, ids, base_frames)
        geometry_report += rope_report

    round_net(cage, membrane, ids)

    # 3. Feed Spreader and Ballistic Feed Pellets
    if use_feed:
        print("GUI_STAGE: Building feed spreader and ballistic pellets…", flush=True)
        from sim2blender.blender.feed import run_feed_animation
        feed_params = dict(feed_cfg) if feed_cfg else {}
        if use_env and isinstance(env_cfg, dict):
            for k in ("current_speed_m_s", "current_direction_deg", "wave_height_m", "wave_period_s", "wave_length_m", "wave_direction_deg", "water_level_m"):
                if k in env_cfg and k not in feed_params:
                    feed_params[k] = env_cfg[k]
        run_feed_animation(feed_params)

    # 4. Fish Schooling / Fish Feeding Interaction
    if use_feeding:
        print("GUI_STAGE: Simulating fish school feeding interaction…", flush=True)
        from sim2blender.blender.fish.feeding import run_fish_feeding_animation
        feeding_params = dict(feeding_cfg)
        if schooling_cfg:
            for k in ("fish_count", "fish_length_mean_m", "fish_length_std_m", "swim_speed_bl_s", "random_seed"):
                if k in schooling_cfg and k not in feeding_params:
                    feeding_params[k] = schooling_cfg[k]
        if use_env and isinstance(env_cfg, dict):
            for k in ("current_speed_m_s", "current_direction_deg", "wave_height_m", "wave_period_s", "wave_length_m", "wave_direction_deg", "water_level_m"):
                if k in env_cfg and k not in feeding_params:
                    feeding_params[k] = env_cfg[k]
        run_fish_feeding_animation(feeding_params)
    elif use_schooling:
        print("GUI_STAGE: Adding salmon / fish schooling…", flush=True)
        from sim2blender.blender.fish.school import run_fish_schooling
        schooling_params = dict(schooling_cfg) if schooling_cfg else {}
        if use_env and isinstance(env_cfg, dict):
            for k in ("current_speed_m_s", "current_direction_deg", "wave_height_m", "wave_period_s", "wave_length_m", "wave_direction_deg", "water_level_m"):
                if k in env_cfg and k not in schooling_params:
                    schooling_params[k] = env_cfg[k]
        run_fish_schooling(schooling_params)

    # 4.5 Ocean Water & Wave/Current Environment (if not already initialized before cloth baking)
    if use_env and not scene.get("hydrodynamics_active"):
        print("GUI_STAGE: Building ocean water below Z = 0 & wave/current hydrodynamics…", flush=True)
        from sim2blender.blender.water import add_water
        from sim2blender.blender.environment import set_wave_and_current

        env_dict = env_cfg if isinstance(env_cfg, dict) else {}
        level = float(env_dict.get("water_level_m", env_dict.get("level", 0.0)))
        depth = float(env_dict.get("water_depth_m", env_dict.get("depth", 100.0)))
        size = float(env_dict.get("water_size_m", env_dict.get("size", 300.0)))

        curr_speed = float(env_dict.get("current_speed_m_s", env_dict.get("current_speed", 0.15)))
        curr_dir = float(env_dict.get("current_direction_deg", env_dict.get("current_dir_deg", 0.0)))
        wave_h = float(env_dict.get("wave_height_m", env_dict.get("wave_height", 0.30)))
        wave_t = float(env_dict.get("wave_period_s", env_dict.get("wave_period", 6.0)))
        wave_l = float(env_dict.get("wave_length_m", env_dict.get("wave_length", 25.0)))
        wave_dir = float(env_dict.get("wave_direction_deg", env_dict.get("wave_dir_deg", 0.0)))

        water_kwargs = {
            "level": level,
            "depth": depth,
            "size": size,
            "enable_volume": bool(env_dict.get("enable_volume", True)),
        }
        for opt in ("surface_resolution", "ior", "roughness", "scatter_density", "absorption_density", "sun_energy", "sun_elevation_deg", "sun_rotation_deg"):
            if opt in env_dict:
                water_kwargs[opt] = env_dict[opt]

        add_water(scene, collection=collection, **water_kwargs)

        set_wave_and_current(
            scene,
            current_speed=curr_speed,
            current_dir_deg=curr_dir,
            wave_height=wave_h,
            wave_period=wave_t,
            wave_length=wave_l,
            wave_dir_deg=wave_dir,
            water_level=level,
            animate_water_surface=True,
        )

    # 5. Cinematic Camera
    if use_camera:
        print("GUI_STAGE: Setting up cinematic camera…", flush=True)
        from sim2blender.blender.camera import setup_cinematic_camera
        setup_cinematic_camera(camera_cfg)


    # 6. Final Shading, View, and Scene Export
    scene.frame_set(1)
    setup_view(scene, points, collection)
    apply_visualization(scene, cage)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = output_path.with_suffix(".geometry.json")
    geometry_report += [
        dict(component_id=c["component_id"], name=c["component_name"], type="membrane", **c["geometry"])
        for c in {c["component_id"]: c for c in membrane}.values()
    ]
    report_path.write_text(json.dumps(geometry_report, indent=2), encoding="utf-8")
    scene["geometry_report"] = str(report_path.resolve())

    if use_replay:
        dur_sec = step_sec * (len(results.times) - 1)
        obj_count = len(model.components) if hasattr(model, 'components') else len({c.get("component_id", i) for i, c in enumerate(model.cells)})
        replay_report = dict(
            steps=len(results.times),
            video_fps=fps,
            structural_step_seconds=step_sec,
            last_sample_frame=replay_frames[-1],
            video_frame_end=scene.frame_end,
            duration_seconds=dur_sec,
            objects=obj_count,
            wave_period_seconds=wave_period,
            structural_frames_per_wave=frames_per_wave,
        )
        output_path.with_suffix(".replay.json").write_text(json.dumps(replay_report, indent=2), encoding="utf-8")
        output_path.with_suffix(".json").write_text(json.dumps(replay_report, indent=2), encoding="utf-8")

    if use_schooling:
        fish_count = int(schooling_cfg.get("fish_count", 1000))
        struct_step = scene.get("structural_step_seconds", 1.0 / scene.render.fps)
        if use_replay:
            dur_sec = struct_step * (len(results.times) - 1)
        else:
            dur_sec = (scene.frame_end - 1) / scene.render.fps if scene.render.fps else 0.0
        fish_report = dict(
            fish_count=fish_count,
            frames=scene.frame_end,
            video_fps=scene.render.fps,
            structural_step_seconds=struct_step,
            duration_seconds=dur_sec,
        )
        output_path.with_suffix(".fish.json").write_text(json.dumps(fish_report, indent=2), encoding="utf-8")
    else:
        output_path.with_suffix(".fish.json").unlink(missing_ok=True)

    print(f"GUI_STAGE: Saving scene to {output_path.name}…", flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path.resolve()))
    print("GUI_STAGE: Build complete", flush=True)


def main(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    parser = argparse.ArgumentParser(description="Sim2Blender unified pipeline runner")
    parser.add_argument("--config", type=Path, help="JSON configuration file containing all job settings")
    parser.add_argument("--config-json", type=str, default=None, help="Raw JSON string containing all job settings")
    args, unknown = parser.parse_known_args(argv)

    if args.config and args.config.is_file():
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
    elif args.config_json:
        cfg = json.loads(args.config_json)
    else:
        raise ValueError("Must provide --config <file> or --config-json <str> with valid configuration settings.")

    build_unified_scene(cfg)


if __name__ == "__main__":
    main()
