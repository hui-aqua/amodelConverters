"""Compatibility launcher; prefer launchers/cli/run_workflow.py."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sim2blender.cli.blender_entry import main

if __name__=='__main__':main()
