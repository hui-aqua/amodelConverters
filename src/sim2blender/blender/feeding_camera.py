"""Feeding Camera setup, optical frustum pyramid volume, and passing pellet detection counter.

Implements a fixed underwater feeding camera with configurable 3D position (default: 2.5, 0, -5),
visual distance limit (default: 2.5m), FHD (16:9) aspect ratio, 3D visual pyramid frustum,
and automated detection and counting of feed pellets traversing the camera's visible volume.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Sequence

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

DEFAULT_FEEDING_CAMERA_CONFIG = {
    "enabled": True,
    "position_x": 2.5,
    "position_y": 0.0,
    "position_z": -5.0,
    "look_at_x": 0.0,
    "look_at_y": 0.0,
    "look_at_z": -5.0,
    "visual_distance_m": 2.5,
    "clip_start_m": 0.1,
    "focal_length_mm": 32.0,
    "sensor_width_mm": 36.0,
    "sensor_height_mm": 20.25,  # 16:9 FHD aspect ratio (36.0 x 20.25)
    "show_frustum_pyramid": True,
    "show_hud_counter": True,
}


def build_camera_lookat_matrix(origin: Vector, target: Vector, roll_deg: float = 0.0) -> Matrix:
    """Compute 4x4 transform matrix orienting a Blender camera (-Z forward, +Y up)."""
    forward = (target - origin).normalized()
    if forward.length == 0.0:
        forward = Vector((0.0, 0.0, -1.0))

    # Blender camera looks down -Z, so camera -Z aligns with 'forward' (i.e. camera +Z aligns with -forward)
    cam_z = -forward

    world_up = Vector((0.0, 0.0, 1.0))
    # If looking almost straight up or down, adjust world_up
    if abs(forward.dot(world_up)) > 0.999:
        world_up = Vector((0.0, 1.0, 0.0))

    cam_x = world_up.cross(cam_z).normalized()
    cam_y = cam_z.cross(cam_x).normalized()

    mat = Matrix((
        (cam_x.x, cam_y.x, cam_z.x, origin.x),
        (cam_x.y, cam_y.y, cam_z.y, origin.y),
        (cam_x.z, cam_y.z, cam_z.z, origin.z),
        (0.0, 0.0, 0.0, 1.0),
    ))
    return mat


def build_frustum_pyramid_mesh(
    focal_length_mm: float,
    sensor_width_mm: float,
    sensor_height_mm: float,
    clip_start_m: float,
    visual_distance_m: float,
    name: str = "Feeding_Camera_Frustum",
) -> bpy.types.Object:
    """Build a pyramid frustum mesh representing the camera's visual detection volume."""
    existing = bpy.data.objects.get(name)
    if existing is not None:
        bpy.data.objects.remove(existing, do_unlink=True)

    # Semi-angles of perspective cone
    tan_half_x = (sensor_width_mm / 2.0) / focal_length_mm
    tan_half_y = (sensor_height_mm / 2.0) / focal_length_mm

    d_near = max(0.01, float(clip_start_m))
    d_far = max(d_near + 0.1, float(visual_distance_m))

    x_near = d_near * tan_half_x
    y_near = d_near * tan_half_y

    x_far = d_far * tan_half_x
    y_far = d_far * tan_half_y

    # Vertices in camera local coordinate space (camera looks down -Z)
    verts = [
        # 0-3: Near plane rectangle
        (-x_near, -y_near, -d_near),
        (x_near, -y_near, -d_near),
        (x_near, y_near, -d_near),
        (-x_near, y_near, -d_near),
        # 4-7: Far plane rectangle at visual_distance_m
        (-x_far, -y_far, -d_far),
        (x_far, -y_far, -d_far),
        (x_far, y_far, -d_far),
        (-x_far, y_far, -d_far),
    ]

    # Faces: near cap, 4 trapezoidal frustum sides, far cap
    faces = [
        # Near cap (facing backward)
        (0, 1, 2, 3),
        # 4 frustum sides
        (0, 4, 5, 1),  # Bottom
        (1, 5, 6, 2),  # Right
        (2, 6, 7, 3),  # Top
        (3, 7, 4, 0),  # Left
        # Far cap (facing forward)
        (4, 7, 6, 5),
    ]

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    obj.display_type = "SOLID"
    obj.color = (0.08, 0.85, 0.75, 0.18)
    obj.show_transparent = True
    obj.show_wire = True
    obj.show_in_front = False
    obj.hide_render = True

    # Assign semi-transparent viewport material
    mat = bpy.data.materials.get(f"{name}_Mat")
    if mat is None:
        mat = bpy.data.materials.new(f"{name}_Mat")
    mat.diffuse_color = obj.color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.08, 0.85, 0.75, 1.0)
        bsdf.inputs["Alpha"].default_value = 0.18
        bsdf.inputs["Roughness"].default_value = 0.6
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    elif hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    obj.data.materials.append(mat)

    return obj


def setup_feeding_camera(
    config: dict | None = None,
    scene: bpy.types.Scene | None = None,
) -> tuple[bpy.types.Object, bpy.types.Object | None, bpy.types.Object | None]:
    """Create or configure the fixed underwater feeding camera, visual pyramid frustum, and HUD text."""
    cfg = {**DEFAULT_FEEDING_CAMERA_CONFIG, **(config or {})}

    # Support either 'position': [x,y,z] or individual 'position_x', 'position_y', 'position_z'
    if "position" in cfg and isinstance(cfg["position"], (list, tuple)) and len(cfg["position"]) == 3:
        pos = Vector(cfg["position"])
    else:
        pos = Vector((
            float(cfg.get("position_x", 2.5)),
            float(cfg.get("position_y", 0.0)),
            float(cfg.get("position_z", -5.0)),
        ))

    # Support either 'target' / 'look_at': [x,y,z] or individual 'look_at_x', etc.
    if "target" in cfg and isinstance(cfg["target"], (list, tuple)) and len(cfg["target"]) == 3:
        target = Vector(cfg["target"])
    elif "look_at" in cfg and isinstance(cfg["look_at"], (list, tuple)) and len(cfg["look_at"]) == 3:
        target = Vector(cfg["look_at"])
    else:
        target = Vector((
            float(cfg.get("look_at_x", 0.0)),
            float(cfg.get("look_at_y", 0.0)),
            float(cfg.get("look_at_z", -5.0)),
        ))

    visual_distance = float(cfg.get("visual_distance_m", 2.5))
    clip_start = float(cfg.get("clip_start_m", 0.1))
    focal_length = float(cfg.get("focal_length_mm", 32.0))
    sensor_w = float(cfg.get("sensor_width_mm", 36.0))
    sensor_h = float(cfg.get("sensor_height_mm", 20.25))
    show_frustum = bool(cfg.get("show_frustum_pyramid", cfg.get("show_frustum", True)))
    show_hud = bool(cfg.get("show_hud_counter", cfg.get("show_counter", True)))

    if scene is None:
        scene = bpy.context.scene

    # Set FHD 16:9 render resolution
    render_w = int(cfg.get("render_width", 1920))
    render_h = int(cfg.get("render_height", 1080))
    scene.render.resolution_x = render_w
    scene.render.resolution_y = render_h

    # Ensure collection exists
    feed_cam_col = bpy.data.collections.get("Feeding_Camera_Rig")
    if feed_cam_col is None:
        feed_cam_col = bpy.data.collections.new("Feeding_Camera_Rig")
        scene.collection.children.link(feed_cam_col)

    # 1. Camera Object
    cam_data = bpy.data.cameras.get("Feeding_Camera_Data")
    if cam_data is None:
        cam_data = bpy.data.cameras.new("Feeding_Camera_Data")

    cam_data.type = "PERSP"
    cam_data.lens = focal_length
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.sensor_width = sensor_w
    cam_data.sensor_height = sensor_h
    cam_data.clip_start = clip_start
    cam_data.clip_end = visual_distance
    cam_data.show_limits = True

    cam_obj = bpy.data.objects.get("Feeding_Camera")
    if cam_obj is None:
        cam_obj = bpy.data.objects.new("Feeding_Camera", cam_data)
        feed_cam_col.objects.link(cam_obj)
    else:
        cam_obj.data = cam_data

    # Set position and orientation looking at target
    mat_world = build_camera_lookat_matrix(pos, target)
    cam_obj.matrix_world = mat_world

    cam_obj["camera_role"] = "feeding_inspection"
    cam_obj["visual_distance_m"] = visual_distance
    cam_obj["look_at_target"] = list(target)

    # 2. Frustum Pyramid Volume Mesh
    frustum_obj = None
    if show_frustum:
        frustum_obj = build_frustum_pyramid_mesh(
            focal_length_mm=focal_length,
            sensor_width_mm=sensor_w,
            # Horizontal sensor fit derives vertical FOV from render aspect,
            # including non-square pixels, just like pellet detection does.
            sensor_height_mm=sensor_w * (render_h * scene.render.pixel_aspect_y)
            / (render_w * scene.render.pixel_aspect_x),
            clip_start_m=clip_start,
            visual_distance_m=visual_distance,
            name="Feeding_Camera_Frustum",
        )
        if frustum_obj.name not in feed_cam_col.objects:
            feed_cam_col.objects.link(frustum_obj)
        frustum_obj.parent = cam_obj
        frustum_obj.matrix_local = Matrix.Identity(4)

    # 3. HUD Counter Text
    hud_obj = None
    if show_hud:
        hud_name = "Feeding_Camera_HUD"
        hud_obj = bpy.data.objects.get(hud_name)
        if hud_obj is None:
            curve_data = bpy.data.curves.new(name=hud_name, type="FONT")
            hud_obj = bpy.data.objects.new(hud_name, curve_data)
            feed_cam_col.objects.link(hud_obj)

        hud_obj.data.body = f"Feeding Camera: Pellets: 0 (Range: {visual_distance}m)"
        hud_obj.data.size = 0.12
        hud_obj.show_in_front = True
        hud_obj.hide_render = True
        hud_obj.parent = cam_obj
        hud_obj.location = Vector((-0.6, 0.35, -0.4))
        hud_obj.rotation_euler = (0.0, 0.0, 0.0)

    return cam_obj, frustum_obj, hud_obj


def count_pellets_in_frustum(
    *args,
    **kwargs,
) -> dict:
    """Analyze pellet trajectories and count unique pellets traversing the camera volume.

    Supports signatures:
        count_pellets_in_frustum(scene, camera_obj, config=None, output_path=None, pellets=None)
        count_pellets_in_frustum(camera_obj, pellets, scene, visual_distance_m, clip_start_m)
    """
    scene: bpy.types.Scene = bpy.context.scene
    camera_obj: bpy.types.Object | None = None
    config: dict | None = None
    output_path: Path | None = None
    custom_pellets: Sequence[bpy.types.Object] | None = None
    override_visual_dist: float | None = None
    override_clip_start: float | None = None

    if len(args) >= 1 and isinstance(args[0], bpy.types.Scene):
        scene = args[0]
        if len(args) >= 2 and isinstance(args[1], bpy.types.Object):
            camera_obj = args[1]
        if len(args) >= 3 and isinstance(args[2], dict):
            config = args[2]
        if len(args) >= 4 and isinstance(args[3], (Path, str)):
            output_path = Path(args[3])
        if len(args) >= 5 and isinstance(args[4], (list, tuple)):
            custom_pellets = list(args[4])
    elif len(args) >= 1 and isinstance(args[0], bpy.types.Object):
        camera_obj = args[0]
        if len(args) >= 2 and isinstance(args[1], (list, tuple)):
            custom_pellets = list(args[1])
        if len(args) >= 3 and isinstance(args[2], bpy.types.Scene):
            scene = args[2]
        if len(args) >= 4 and isinstance(args[3], (int, float)):
            override_visual_dist = float(args[3])
        if len(args) >= 5 and isinstance(args[4], (int, float)):
            override_clip_start = float(args[4])

    if "scene" in kwargs:
        scene = kwargs["scene"]
    if "camera_obj" in kwargs:
        camera_obj = kwargs["camera_obj"]
    if "config" in kwargs:
        config = kwargs["config"]
    if "output_path" in kwargs and kwargs["output_path"]:
        output_path = Path(kwargs["output_path"])
    if "pellets" in kwargs and kwargs["pellets"]:
        custom_pellets = list(kwargs["pellets"])

    if camera_obj is None:
        camera_obj = bpy.data.objects.get("Feeding_Camera")
    if camera_obj is None:
        raise ValueError("No feeding camera object found in scene.")

    cfg = {**DEFAULT_FEEDING_CAMERA_CONFIG, **(config or {})}
    visual_distance = (
        override_visual_dist
        if override_visual_dist is not None
        else float(cfg.get("visual_distance_m", camera_obj.data.clip_end))
    )
    clip_start = (
        override_clip_start
        if override_clip_start is not None
        else float(cfg.get("clip_start_m", camera_obj.data.clip_start))
    )
    show_hud = bool(cfg.get("show_hud_counter", cfg.get("show_counter", True)))

    if custom_pellets is not None:
        pellets = [p for p in custom_pellets if isinstance(p, bpy.types.Object)]
    else:
        particle_col = bpy.data.collections.get("FishFeed_Proxy_Particles")
        pellets = [o for o in particle_col.objects if o.type == "MESH"] if particle_col else []

    fps = scene.render.fps / scene.render.fps_base if scene.render.fps_base else scene.render.fps
    f_start = int(scene.frame_start)
    f_end = int(scene.frame_end)

    unique_pellets = set()
    counts_per_frame: dict[int, int] = {}
    transit_events: list[dict] = []
    pellet_first_seen: dict[str, int] = {}
    pellet_last_seen: dict[str, int] = {}

    cam_pos = camera_obj.matrix_world.translation.copy()

    for frame in range(f_start, f_end + 1):
        scene.frame_set(frame)
        visible_count = 0

        for p in pellets:
            # Check visibility drivers (unborn or consumed/expired pellets are hidden)
            if p.hide_viewport or p.hide_render:
                continue

            pos_world = p.matrix_world.translation
            coord_cam = world_to_camera_view(scene, camera_obj, pos_world)
            u, v, d = coord_cam.x, coord_cam.y, coord_cam.z

            # Check inside camera frustum bounds (0 <= u, v <= 1) and depth within visual distance
            if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0 and clip_start <= d <= visual_distance:
                visible_count += 1
                unique_pellets.add(p.name)

                if p.name not in pellet_first_seen:
                    pellet_first_seen[p.name] = frame
                    transit_events.append({
                        "pellet": p.name,
                        "entry_frame": frame,
                        "entry_time_s": round(frame / fps, 4),
                        "distance_m": round(d, 3),
                        "viewport_uv": [round(u, 3), round(v, 3)],
                    })
                pellet_last_seen[p.name] = frame

        counts_per_frame[frame] = visible_count

    total_unique = len(unique_pellets)
    total_evaluated = len(pellets)
    detection_ratio = (total_unique / total_evaluated * 100.0) if total_evaluated > 0 else 0.0

    pellet_details = {
        evt["pellet"]: {
            **evt,
            "exit_frame": pellet_last_seen.get(evt["pellet"], evt["entry_frame"]),
        }
        for evt in transit_events
    }

    report = {
        "camera_name": camera_obj.name,
        "position": [round(cam_pos.x, 3), round(cam_pos.y, 3), round(cam_pos.z, 3)],
        "camera_position": [round(cam_pos.x, 3), round(cam_pos.y, 3), round(cam_pos.z, 3)],
        "look_at_target": list(camera_obj.get("look_at_target", [0.0, 0.0, -5.0])),
        "visual_distance_m": visual_distance,
        "clip_start_m": clip_start,
        "aspect_ratio": "16:9 (FHD)",
        "frames_evaluated": f_end - f_start + 1,
        "fps": fps,
        "total_pellets_emitted": total_evaluated,
        "total_unique_pellets_detected": total_unique,
        "detection_ratio_percent": round(detection_ratio, 2),
        "counts_per_frame": counts_per_frame,
        "transit_events": transit_events,
        "pellet_details": pellet_details,
    }

    # Store on camera object and scene metadata
    camera_obj["total_pellets_detected"] = total_unique
    camera_obj["detection_ratio_percent"] = round(detection_ratio, 2)
    scene["feeding_camera_pellet_count"] = total_unique

    # 3. Optional 3D Viewport HUD Counter Text
    if show_hud:
        hud_name = "Feeding_Camera_HUD"
        hud_obj = bpy.data.objects.get(hud_name)
        if hud_obj is None:
            curve_data = bpy.data.curves.new(name=hud_name, type="FONT")
            hud_obj = bpy.data.objects.new(hud_name, curve_data)
            feed_cam_col = bpy.data.collections.get("Feeding_Camera_Rig") or scene.collection
            feed_cam_col.objects.link(hud_obj)

        hud_obj.data.body = f"Feeding Camera: Pellets: {total_unique} (Range: {visual_distance}m)"
        hud_obj.data.size = 0.12
        hud_obj.show_in_front = True
        hud_obj.hide_render = True
        hud_obj.parent = camera_obj
        hud_obj.location = Vector((-0.6, 0.35, -0.4))
        hud_obj.rotation_euler = (0.0, 0.0, 0.0)

    # Export JSON report
    if output_path is not None:
        report_file = output_path.with_suffix(".feeding_camera.json")
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        scene["feeding_camera_report"] = str(report_file.resolve())

    print(
        f"FEEDING_CAMERA_DONE DETECTED {total_unique}/{total_evaluated} PELLETS "
        f"({detection_ratio:.1f}%) AT RANGE {visual_distance}m",
        flush=True,
    )
    return report
