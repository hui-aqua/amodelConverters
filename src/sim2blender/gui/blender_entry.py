"""Compatibility bridge for older desktop model commands."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from sim2blender.cli.blender_entry import main as dispatch

def main():
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    dispatch(['model',*args])

if __name__=='__main__':main()
