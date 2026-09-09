"""Compatibility entry point for the replay_geometry workflow."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sim2blender.workflows.replay_geometry import main
if __name__ == '__main__':
    main()
