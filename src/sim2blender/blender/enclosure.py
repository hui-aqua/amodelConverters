"""Topology repair, virtual caps and whole-object containment."""
import math

def stitch_membrane_seams(faces, points, tolerance=.005):
    """Split coarse boundary edges along matching finer source edges.

    Only accept a complete, unique boundary chain within 5 mm and 1% of the
    coarse edge length (rounded coordinates and curved seams). Keep all source nodes
    and one polygon per source element; never bridge an unrelated opening.
    """
    from collections import Counter, defaultdict
    from mathutils import Vector
    edges = Counter(tuple(sorted((a, b))) for f in faces for a, b in zip(f, f[1:] + f[:1]))
    adjacent = defaultdict(set)
    for (a, b), count in edges.items():
        if count == 1:
            adjacent[a].add(b)
            adjacent[b].add(a)
    vectors = [Vector(p) for p in points]
    replacements = {}
    for a, b in sorted(e for e, count in edges.items() if count == 1):
        delta = vectors[b] - vectors[a]
        length2 = delta.length_squared
        if length2 <= tolerance * tolerance:
            continue
        along = {a: 0., b: 1.}
        for n in adjacent:
            if n in (a, b):
                continue
            t = (vectors[n] - vectors[a]).dot(delta) / length2
            if 0 < t < 1 and (vectors[n] - vectors[a] - t * delta).length <= min(tolerance, math.sqrt(length2)*.01):
                along[n] = t
        chain = [a]
        while chain[-1] != b:
            current = chain[-1]
            candidates = [n for n in adjacent[current] if n in along and along[n] > along[current]
                          and not (current == a and n == b)]
            if len(candidates) != 1:
                break
            chain.append(candidates[0])
        if chain[-1] == b and len(chain) > 2:
            replacements[a, b] = chain[1:-1]
            replacements[b, a] = list(reversed(chain[1:-1]))
    result = []
    for face in faces:
        expanded = []
        for a, b in zip(face, face[1:] + face[:1]):
            expanded.append(a)
            expanded.extend(replacements.get((a, b), ()))
        result.append(tuple(expanded))
    return result


def boundary_caps(faces, points, allow_caps=False):
    """Close simple planar boundary loops; never hide nonmanifold geometry."""
    from collections import Counter, defaultdict
    from mathutils import Vector
    edges = Counter(tuple(sorted((a, b))) for f in faces for a, b in zip(f, f[1:] + f[:1]))
    if any(n > 2 for n in edges.values()):
        raise ValueError('Nonmanifold membrane shell: select an enclosing subset with --membrane-ids.')
    adjacent = defaultdict(list)
    for (a, b), count in edges.items():
        if count == 1:
            adjacent[a].append(b)
            adjacent[b].append(a)
    if adjacent and not allow_caps:
        raise ValueError('Membrane shell is open. Use --cap-openings to explicitly add virtual containment caps.')
    if any(len(v) != 2 for v in adjacent.values()):
        raise ValueError('Membrane boundary is branched; repair the source mesh.')
    caps = []
    remaining = set(adjacent)
    while remaining:
        start = min(remaining)
        loop = [start]
        previous, current = start, adjacent[start][0]
        while current != start:
            if current in loop:
                raise ValueError('Invalid membrane boundary loop')
            loop.append(current)
            neighbors = adjacent[current]
            previous, current = current, next(n for n in neighbors if n != previous)
        remaining.difference_update(loop)
        origin = Vector(points[loop[0]])
        normal = Vector((0, 0, 0))
        for a, b in zip(loop, loop[1:] + loop[:1]):
            normal += (Vector(points[a]) - origin).cross(Vector(points[b]) - origin)
        if normal.length < 1e-8:
            raise ValueError('Degenerate boundary cap')
        normal.normalize()
        if max(abs((Vector(points[n]) - origin).dot(normal)) for n in loop) > 1e-3:
            raise ValueError('Nonplanar opening: repair the shell before adding fish')
        caps.append(tuple(loop))
    return caps


class Enclosure:
    """BVH parity containment plus conservative whole-fish clearance."""
    def __init__(self, points, faces):
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        from mathutils.geometry import tessellate_polygon
        self.points = [Vector(p) for p in points]
        # Tessellate concave caps as well as ordinary membrane polygons.
        triangles = []
        vertices = []
        for face in faces:
            for tri in tessellate_polygon([[self.points[i] for i in face]]):
                base = len(vertices)
                # Blender 5.2 returns polygon-local indices; earlier releases
                # returned vectors.
                vertices.extend(self.points[face[v]] if isinstance(v, int) else v for v in tri)
                triangles.append((base, base + 1, base + 2))
        self.bvh = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
        used = {i for f in faces for i in f}
        self.low = Vector(tuple(min(self.points[i][a] for i in used) for a in range(3)))
        self.high = Vector(tuple(max(self.points[i][a] for i in used) for a in range(3)))
        # BVH math is float32: advancing by less than an ULP at large source
        # coordinates can hit the same triangle forever.
        self.epsilon = max((self.high - self.low).length * 1e-7,
                           max(abs(v) for p in (self.low, self.high) for v in p) * 1e-6, 1e-7)

    def contains(self, point, radius=0):
        from mathutils import Vector
        point = Vector(point)
        if any(point[a] < self.low[a] or point[a] > self.high[a] for a in range(3)):
            return False
        nearest = self.bvh.find_nearest(point)
        if nearest[0] is None or nearest[3] <= radius + self.epsilon:
            return False
        votes = 0
        for direction in ((1, .371, .529), (.217, 1, .413), (.319, .173, 1)):
            direction = Vector(direction).normalized()
            origin = point.copy()
            hits = 0
            previous_face = None
            for _ in range(10000):
                hit = self.bvh.ray_cast(origin, direction)
                if hit[0] is None:
                    break
                if hit[2] == previous_face:
                    # Ambiguous grazing/repeated intersection: reject this
                    # candidate conservatively rather than guessing parity.
                    return False
                previous_face = hit[2]
                hits += 1
                origin = hit[0] + direction * self.epsilon
            else:
                return False
            votes += hits % 2
        return votes >= 2

    def sample(self, rng, radius):
        from mathutils import Vector
        for _ in range(20000):
            point = Vector(tuple(rng.uniform(self.low[a], self.high[a]) for a in range(3)))
            if self.contains(point, radius):
                return point
        raise ValueError('No safe fish position found: check enclosure and fish size.')


