"""Shared plotting entry point; optional matplotlib dependency."""
from pathlib import Path
import argparse
from sim2blender.io.aquasim.model import DEFAULT_INPUT, PROJECT_ROOT, read_model


def main():
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    parser = argparse.ArgumentParser(description='Plot active AModel nodes and components')
    parser.add_argument('input', nargs='?', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('-o', '--output', type=Path)
    parser.add_argument('--nodes-only', action='store_true')
    args = parser.parse_args()
    args.output = args.output or PROJECT_ROOT/'output'/args.input.with_suffix('.png').name
    args.output.parent.mkdir(parents=True, exist_ok=True)
    components = not args.nodes_only
    model = read_model(args.input)
    if not model.nodes:
        raise ValueError('No active geometry to plot')
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    points = [n.point for n in model.nodes.values()]
    ax.scatter(*zip(*points), s=1, c='black', label='Nodes')
    fixed = [n.point for n in model.nodes.values() if not all(n.translate)]
    if fixed:
        ax.scatter(*zip(*fixed), s=8, c='orange', label='Constrained nodes')
    if components:
        for tag, color in [('beam', 'blue'), ('truss', 'red'), ('membrane', 'green')]:
            segments = []
            for cell in model.cells:
                if cell['component_tag'] == tag:
                    ids = cell['nodes']
                    if tag == 'membrane':
                        ids = ids + ids[:1]
                    segments.append([model.nodes[n].point for n in ids])
            if segments:
                ax.add_collection3d(Line3DCollection(segments, colors=color, linewidths=.5, label=tag))
    low = [min(p[a] for p in points) for a in range(3)]
    high = [max(p[a] for p in points) for a in range(3)]
    ax.set_box_aspect([max(hi-lo, .001) for lo,hi in zip(low,high)])
    ax.set(xlabel='X', ylabel='Y', zlabel='Z')
    ax.legend()
    fig.savefig(args.output)
    plt.close(fig)
    print(f'Saved: {args.output}')


if __name__ == "__main__":
    main()
