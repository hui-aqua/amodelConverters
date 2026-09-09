"""Blender entry point: -- model ..., -- replay ..., or -- fish ..."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow', choices=('model', 'replay', 'fish'))
    args = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    selected = parser.parse_args(args[:1])
    from importlib import import_module
    module = {'model': 'model_physics', 'replay': 'replay_geometry', 'fish': 'replay_fish'}[selected.workflow]
    import_module('sim2blender.workflows.'+module).main(args[1:])


if __name__ == '__main__':
    main()
