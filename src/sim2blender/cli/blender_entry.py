"""Shared Blender entry point: model, replay, fish, or replay-scene."""
from pathlib import Path
import sys

# Also supports Blender --python with an installed package or source checkout.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

WORKFLOWS={'model':'model_physics','replay':'replay_geometry',
           'fish':'replay_fish','replay-scene':'replay_pipeline'}


def main(argv=None):
    import argparse
    from importlib import import_module
    if argv is None:
        argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow',choices=WORKFLOWS)
    selected=parser.parse_args(argv[:1])
    import_module('sim2blender.workflows.'+WORKFLOWS[selected.workflow]).main(argv[1:])


if __name__=='__main__':main()
