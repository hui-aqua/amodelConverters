"""Export active AModel geometry in source XYZ coordinates."""
from sim2blender.io.aquasim.model import cli, read_model


def write_obj(path, model):
    ids, points, lines, faces = model.legacy()
    with open(path, 'w', encoding='utf-8') as stream:
        stream.write('# Active AModel geometry; source XYZ. Use scripts/build_scene.py for dynamics.\n')
        for p in points:
            stream.write('v ' + ' '.join(map(str, p)) + '\n')
        for cells, prefix in ((lines, 'l'), (faces, 'f')):
            for cell in cells:
                stream.write(prefix + ' ' + ' '.join(str(i+1) for i in cell['points']) + '\n')


def main():
    args = cli(__doc__, '.obj')
    write_obj(args.output, read_model(args.input))
    print(f'Saved: {args.output}')


if __name__ == '__main__':
    main()
