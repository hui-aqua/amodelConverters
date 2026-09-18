"""Launch the optional desktop frontend from a source checkout."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))

if __name__=='__main__':
    from sim2blender.gui.app import main
    main()
