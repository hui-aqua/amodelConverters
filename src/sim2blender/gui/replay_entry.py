"""Compatibility bridge; orchestration is shared in workflows/replay_pipeline.py."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from sim2blender.workflows.replay_pipeline import main

if __name__=='__main__':main()
