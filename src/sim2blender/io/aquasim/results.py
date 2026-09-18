"""Read AquaSim Time/VID/X/Y/Z exports and match their initial coordinates."""
from dataclasses import dataclass
import math
from sim2blender.core.timeline import sample_frames


@dataclass
class Results:
    times: list
    positions: list


def iter_result_samples(path):
    """Validate and stream one structural sample at a time (bounded memory)."""
    current_time=None
    current={}
    first_ids=None
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
                if current_time is None or t != current_time:
                    if current_time is not None and t <= current_time:
                        raise ValueError('time must increase')
                    if current_time is not None:
                        if first_ids is None:first_ids=set(current)
                        if current.keys()!=first_ids:raise ValueError('Result node IDs differ between steps')
                        yield current_time,current
                    current_time=t
                    current={}
                if vid in current:
                    raise ValueError('duplicate VID')
                current[vid] = point
            except ValueError as exc:
                raise ValueError(f'{path}:{number}: {exc}') from exc
    if current_time is None:
        raise ValueError('No result samples')
    if first_ids is not None and current.keys()!=first_ids:
        raise ValueError('Result node IDs differ between steps')
    yield current_time,current


def read_results(path):
    times,positions=[],[]
    for t,points in iter_result_samples(path):
        times.append(t);positions.append(points)
    return Results(times, positions)


def inspect_results(path, cancelled=None):
    """Count distinct structural time blocks, not per-node coordinate rows."""
    count=0
    for t,points in iter_result_samples(path):
        if cancelled and cancelled():raise InterruptedError('Results inspection cancelled')
        if count==0:first=t
        count+=1
    return dict(samples=count,nodes_per_sample=len(points),first_label=first,last_label=t)


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
