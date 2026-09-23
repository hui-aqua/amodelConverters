"""Interactive 3D Model & Color Inspection in Blender before Scene Building.

Visualizes the AquaSim cage reference geometry alongside all imported OBJ models
(rotor, stationary base, custom equipment), setting up viewport Material Preview
and an interactive N-Panel to inspect dimensions, materials, and (X, Y, Z) positions.

Can be run via command line:
    blender --python scripts/blender/blender_model_preview.py -- --config preview_config.json
    blender --python scripts/blender/blender_model_preview.py -- --model cage.amodel --move-obj spreader_move.obj --still-obj spreader_still.obj --z-offset 0.52
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import bpy


def _ensure_sim2blender_in_path() -> None:
    for start in [Path(__file__).resolve() if "__file__" in globals() and __file__ else Path.cwd().resolve()]:
        curr = start if start.is_dir() else start.parent
        for _ in range(6):
            src_dir = curr / "src"
            if (src_dir / "sim2blender").is_dir():
                src_str = str(src_dir)
                if src_str not in sys.path:
                    sys.path.insert(0, src_str)
                return
            if curr.parent == curr:
                break
            curr = curr.parent


_ensure_sim2blender_in_path()

from sim2blender.blender.model_preview import build_model_preview_scene


def parse_arguments() -> tuple[dict, bool]:
    argv = sys.argv
    cli_args = []
    if "--" in argv:
        cli_args = argv[argv.index("--") + 1:]

    parser = argparse.ArgumentParser(description="Sim2Blender 3D Model & Color Preview")
    parser.add_argument("--config", help="Path to JSON preview configuration file")
    parser.add_argument("--model", help="Path to AquaSim .amodel cage file")
    parser.add_argument("--move-obj", help="Path to spreader_move.obj")
    parser.add_argument("--still-obj", help="Path to spreader_still.obj")
    parser.add_argument("--obj", action="append", help="Extra OBJ in format 'path' or 'path:name:x,y,z'")
    parser.add_argument("--water-level", type=float, default=0.0, help="Water level Z (m)")
    parser.add_argument("--z-offset", type=float, default=0.52, help="Spreader lift offset (m)")
    parser.add_argument("--save-blend", help="Path to save or open checked preview .blend file")
    parser.add_argument("--force-rebuild", action="store_true", help="Force rebuilding preview scene from scratch even if checked blend exists")
    parser.add_argument("--no-ui", action="store_true", help="Do not register interactive N-panel UI")

    args = parser.parse_args(cli_args)

    config = {
        "model_path": None,
        "water_level_z": args.water_level,
        "include_water": True,
        "obj_models": [],
        "setup_ui": not args.no_ui,
        "setup_lighting": True,
    }

    if args.config and Path(args.config).is_file():
        with open(args.config, "r", encoding="utf-8") as f:
            cfg_data = json.load(f)
            config.update(cfg_data)
            if args.no_ui:
                config["setup_ui"] = False
        return config, args.no_ui

    if args.model:
        config["model_path"] = args.model

    z_tot = args.water_level + args.z_offset
    if args.move_obj and Path(args.move_obj).is_file():
        config["obj_models"].append({
            "path": args.move_obj,
            "name": "Spreader_Rotor",
            "position": [0.0, 0.0, z_tot],
        })

    if args.still_obj and Path(args.still_obj).is_file():
        config["obj_models"].append({
            "path": args.still_obj,
            "name": "Spreader_Base",
            "position": [0.0, 0.0, z_tot],
        })

    if args.obj:
        for extra in args.obj:
            parts = extra.split(":")
            p_path = parts[0]
            p_name = parts[1] if len(parts) > 1 else Path(p_path).stem
            p_pos = [0.0, 0.0, 0.0]
            if len(parts) > 2:
                try:
                    p_pos = [float(v) for v in parts[2].split(",")]
                except ValueError:
                    pass
            config["obj_models"].append({
                "path": p_path,
                "name": p_name,
                "position": p_pos,
            })

    if args.save_blend:
        config["save_blend_path"] = args.save_blend
    if args.force_rebuild:
        config["force_rebuild"] = True

    return config, args.no_ui


def main() -> None:
    config, no_ui = parse_arguments()

    print("\n" + "=" * 60)
    print("SIM2BLENDER 3D MODEL & COLOR PREVIEW (PRE-BUILD CHECK)")
    print("=" * 60)
    if config.get("model_path"):
        print(f"  AquaSim Cage:   {config['model_path']}")
    print(f"  Water Level Z:  {config.get('water_level_z', 0.0):.2f} m")
    print(f"  OBJ Models:     {len(config.get('obj_models', []))}")
    for m in config.get("obj_models", []):
        print(f"    - {m.get('name')}: {m.get('path')} @ {m.get('position')}")
    if config.get("save_blend_path"):
        print(f"  Checked Scene:  {config.get('save_blend_path')}")
    print("=" * 60 + "\n")

    save_path = config.get("save_blend_path")
    if save_path:
        save_file = Path(save_path).resolve()
        if save_file.is_file() and not config.get("force_rebuild", False):
            print(f"Loading existing checked Blender file: {save_file}")
            bpy.ops.wm.open_mainfile(filepath=str(save_file))
            from sim2blender.blender.model_preview import (
                register_model_inspector_ui,
                setup_viewport_shading_material_preview,
            )
            if config.get("setup_ui", True):
                register_model_inspector_ui()
                setup_viewport_shading_material_preview()
            print("Loaded saved model adjustments. Ready for visual inspection.")
            return

    summary = build_model_preview_scene(config)

    print(f"Preview built: {summary['total_models']} models loaded.")
    if summary["cage_objects"]:
        print(f"  Cage: {summary['cage_objects']}")
    if summary["obj_objects"]:
        print(f"  OBJs: {summary['obj_objects']}")
    if summary.get("saved_blend_file"):
        print(f"  Saved to: {summary['saved_blend_file']}")
    print("Viewport configured to Material Preview (EEVEE). Ready for visual inspection.")


if __name__ == "__main__":
    main()

