"""Interactive Spreader Water Line Visualization & Calibration in Blender.

Visualizes the spreader model (rotor arm & stationary base) together with the ocean
water surface plane and measurement indicators, allowing interactive calibration
of the water line Z offset.

Can be run directly inside Blender's Scripting workspace OR via command line:
    blender --python scripts/blender/blender_spreader_waterline.py
    blender scene.blend --python scripts/blender/blender_spreader_waterline.py -- --z-offset 0.52
"""

from __future__ import annotations

import argparse
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

from sim2blender.blender.feed import (
    DEFAULT_SPREADER_MOVE_PATH,
    DEFAULT_SPREADER_STILL_PATH,
)
from sim2blender.blender.spreader_waterline import visualize_spreader_waterline

# -----------------------------------------------------------------------------
# Configuration (defaults can be overridden via CLI args after '--')
# -----------------------------------------------------------------------------
SPREADER_MOVE_OBJ = DEFAULT_SPREADER_MOVE_PATH
SPREADER_STILL_OBJ = DEFAULT_SPREADER_STILL_PATH
SPREADER_Z_OFFSET = 0.52   # Spreader lift above water line (meters)
WATER_LEVEL_Z = 0.0        # Ocean water surface elevation (meters)
WATER_SIZE = 6.0           # Preview water surface width (meters)


def parse_arguments() -> argparse.Namespace:
    argv = sys.argv
    cli_args = []
    if "--" in argv:
        cli_args = argv[argv.index("--") + 1:]

    parser = argparse.ArgumentParser(description="Sim2Blender Spreader Water Line Calibration")
    parser.add_argument("--move-obj", default=SPREADER_MOVE_OBJ, help="Path to spreader_move.obj")
    parser.add_argument("--still-obj", default=SPREADER_STILL_OBJ, help="Path to spreader_still.obj")
    parser.add_argument("--z-offset", type=float, default=SPREADER_Z_OFFSET, help="Water line lift offset (m)")
    parser.add_argument("--water-level", type=float, default=WATER_LEVEL_Z, help="Water surface level Z (m)")
    parser.add_argument("--water-size", type=float, default=WATER_SIZE, help="Water surface preview size (m)")
    parser.add_argument("--heave-rao", type=float, default=0.5, help="Heave Response Amplitude Operator (default 0.5)")
    parser.add_argument("--wave-height", type=float, default=0.0, help="Wave height for heave motion animation (m)")
    parser.add_argument("--wave-period", type=float, default=5.0, help="Wave period for heave motion animation (s)")
    parser.add_argument("--no-ui", action="store_true", help="Do not register interactive N-panel UI")
    return parser.parse_args(cli_args)


def main() -> None:
    args = parse_arguments()

    print("\n" + "=" * 60)
    print("SIM2BLENDER SPREADER WATER LINE CALIBRATION")
    print("=" * 60)
    print(f"  Rotor Move OBJ:   {args.move_obj}")
    print(f"  Stationary OBJ:   {args.still_obj}")
    print(f"  Spreader Z Lift:  +{args.z_offset:.3f} m")
    print(f"  Water Level Z:    {args.water_level:.2f} m")
    print(f"  Heave RAO:        {args.heave_rao:.2f}")
    if args.wave_height > 0:
        print(f"  Wave Height:      {args.wave_height:.2f} m (Period: {args.wave_period:.1f}s)")
    print(f"  Total Elevation:  {args.water_level + args.z_offset:.3f} m")
    print("=" * 60)

    res = visualize_spreader_waterline(
        move_obj_path=args.move_obj,
        still_obj_path=args.still_obj,
        z_offset=args.z_offset,
        water_level_z=args.water_level,
        water_size=args.water_size,
        setup_interactive_ui=not args.no_ui,
        setup_camera_and_lighting=True,
        heave_rao=args.heave_rao,
        wave_height=args.wave_height,
        wave_period=args.wave_period,
        animate_heave=args.wave_height > 0,
    )

    print("\n[SUCCESS] Spreader waterline scene generated successfully!")
    print(f"  Root object:     {res['root'].name}")
    print(f"  Lowest vertex Z: {res['bottom_z']:.4f} m")
    print(f"  Discharge tip:   {res['outlet_tip']}")
    print("\n[TIP] Open 3D Viewport Sidebar: Press 'N' -> 'Sim2Blender' tab")
    print("      to interactively drag and calibrate the Water Line Lift slider!\n")


if __name__ == "__main__":
    main()
