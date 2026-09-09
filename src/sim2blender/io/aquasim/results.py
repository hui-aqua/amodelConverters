"""Read AquaSim Time/VID/X/Y/Z exports and match their initial coordinates."""
from dataclasses import dataclass
import math
from sim2blender.core.timeline import sample_frames


@dataclass
class Results:
    times: list
    positions: list


def read_results(path):
    times, positions = [], []
    with open(path, encoding='utf-8-sig') as source:
        header = next(source, '')
        if header.split() != ['Time', '[-]', 'VID', '[-]', 'X', 'Y', 'Z']:
            raise ValueError('Expected AquaSim Time [-] VID [-] X Y Z header')
        for number, line in enumerate(source, 2):
            if not line.strip():
                continue
            try:
                t, vid, x, y, z = line.split()
                t, vid, point = float(t), int(vid), (float(x), float(y), float(z))
                if not all(math.isfinite(v) for v in (t, *point)):
                    raise ValueError('nonfinite value')
                if not times or t != times[-1]:
                    if times and t <= times[-1]:
                        raise ValueError('time must increase')
                    times.append(t)
                    positions.append({})
                if vid in positions[-1]:
                    raise ValueError('duplicate VID')
                positions[-1][vid] = point
            except ValueError as exc:
                raise ValueError(f'{path}:{number}: {exc}') from exc
    if not times:
        raise ValueError('No result samples')
    if any(p.keys() != positions[0].keys() for p in positions):
        raise ValueError('Result node IDs differ between steps')
    return Results(times, positions)


def map_nodes(model, results):
    """Match model coordinates to the export's three-decimal initial positions.

    VID is a solver index, not an AModel node ID. Never silently use it as one.
    """
    lookup = {}
    for vid, point in results.positions[0].items():
        lookup.setdefault(tuple(round(v, 3) for v in point), []).append(vid)
    mapping = {}
    for nid, node in model.nodes.items():
        candidates = lookup.get(tuple(round(v, 3) for v in node.point), [])
        if len(candidates) != 1:
            raise ValueError(f'Model node {nid}: expected one initial-position match, got {candidates}')
        mapping[nid] = candidates[0]
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('Multiple model nodes match the same result VID')
    return mapping
