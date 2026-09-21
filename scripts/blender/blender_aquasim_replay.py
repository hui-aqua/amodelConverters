"""Replay AquaSim simulation results onto Blender cage mesh.

Replaces the model's nodes movement with AquaSim exported results (e.g. out.txt)
using shape keys evaluated over the wave timeline.

Can be run directly from Blender GUI Scripting workspace OR via Terminal command:
    blender scene.blend --python scripts/blender_aquasim_replay.py
"""

from __future__ import annotations

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

from sim2blender.blender.replay import apply_aquasim_replay

# -----------------------------------------------------------------------------
# 回放参数配置 (AquaSim Replay Configuration)
# -----------------------------------------------------------------------------
DEFAULT_RESULTS_FILE = "examples/models/out.txt"
VIDEO_FPS = 25
WAVE_PERIOD_S = 5.0
FRAMES_PER_WAVE = 40


def main() -> None:
    results_file = DEFAULT_RESULTS_FILE
    if len(sys.argv) > 1 and sys.argv[-1].endswith(".txt"):
        results_file = sys.argv[-1]
    apply_aquasim_replay(
        results_path=results_file,
        wave_period=WAVE_PERIOD_S,
        frames_per_wave=FRAMES_PER_WAVE,
        fps=VIDEO_FPS,
    )


if __name__ == "__main__":
    main()
