"""Arrange flowers, leaves, stems and ribbon into a hand-tied bouquet.

Silhouette (matching the reference): a rounded spray of colourful heads on
top, a skirt of bright leaves underneath, and every stem converging into a
long, slim bundle tied with a pink ribbon.

Placement aims to look arranged by hand: heads sit on a gently domed cap
with only small, irregular offsets; a large focal rose crowns the centre and
heads get a little smaller toward the rim; and colours are dealt out so no
two neighbours share a colour family. Lavender and baby's breath go into the
gaps that are left.

Every head also records a bloom centre, axis and start delay so the renderer
can open it from a closed bud (all heads together).
"""

import numpy as np

import flowers as F

# Palette ------------------------------------------------------------------
ROSES = {
    'red': ((1.0, 0.12, 0.18), (0.55, 0.0, 0.06)),
    'pink': ((1.0, 0.5, 0.78), (0.85, 0.15, 0.5)),
    'hotpink': ((1.0, 0.2, 0.6), (0.65, 0.02, 0.35)),
    'orange': ((1.0, 0.55, 0.12), (0.85, 0.25, 0.02)),
    'yellow': ((1.0, 0.9, 0.25), (0.9, 0.6, 0.05)),
    'white': ((1.0, 0.98, 0.95), (0.85, 0.8, 0.72)),
}
WHITE = (1.0, 0.99, 0.96)
YELLOW = (1.0, 0.86, 0.15)
PURPLE = (0.7, 0.38, 1.0)
MAGENTA = (1.0, 0.3, 0.85)
LEAF_GREENS = [(0.45, 1.0, 0.4), (0.3, 0.9, 0.35), (0.62, 1.0, 0.42),
               (0.28, 0.8, 0.3)]
STEM_GREEN = (0.35, 0.8, 0.35)

SPRAY_C = np.array([0.0, -0.42, 0.0])  # centre of the cap the heads sit on
SPRAY_R = 0.8
SQUASH = 0.92                           # dome height relative to its radius
BIND = np.array([0.0, -0.98, 0.0])      # where the stems are tied together
STEM_BOTTOM = -1.75


def _head(kind, rng, s=1.0):
    if kind in ROSES:
        return F.rose(*ROSES[kind], size=0.2 * s, rng=rng)
    if kind == 'daisy':
        return F.daisy(WHITE, YELLOW, n_petals=12, radius=0.185 * s, petal_w=0.12,
                       layers=1, n_center=300, rng=rng)
    if kind == 'sun':
        return F.daisy(YELLOW, (0.55, 0.25, 0.05), n_petals=18, radius=0.18 * s,
                       petal_w=0.12, droop=0.3, layers=1, n_center=300, rng=rng)
    if kind == 'aster':
        return F.daisy(PURPLE, (1.0, 0.85, 0.2), n_petals=18, radius=0.15 * s,
                       petal_w=0.14, droop=0.5, layers=2, n_center=200, rng=rng)
    if kind == 'cosmos':
        return F.daisy(MAGENTA, (1.0, 0.8, 0.15), n_petals=8, radius=0.17 * s,
                       petal_w=0.38, droop=0.15, cup=0.6, notch=True, layers=1,
                       n_center=200, rng=rng)
    raise ValueError(kind)


KINDS = ['red', 'pink', 'hotpink', 'orange', 'yellow', 'white', 'daisy',
         'sun', 'aster', 'cosmos', 'pink', 'hotpink', 'red', 'cosmos']
FAMILY = {'red': 'red', 'pink': 'pink', 'hotpink': 'pink', 'cosmos': 'pink',
          'orange': 'warm', 'yellow': 'warm', 'sun': 'warm',
          'white': 'white', 'daisy': 'white', 'aster': 'purple'}


def cap_point(psi, az, r=SPRAY_R):
    return SPRAY_C + r * np.array([np.sin(psi) * np.cos(az), np.cos(psi) * SQUASH,
                                   np.sin(psi) * np.sin(az)])


def build(seed=7):
    rng = np.random.default_rng(seed)
    parts = []

    def add(part, sway=1.0):
        part.phase[:] = rng.uniform(0, F.TAU)
        h = np.clip(part.pos[:, 1] - BIND[1], 0, None)
        part.sway[:] = sway * h
        parts.append(part)

    def stem_to_bind(top):
        """Stem from a head down to the tie point, bowing in naturally."""
        ctrl = BIND + (top - BIND) * np.array([0.25, 0.55, 0.25])
        end = BIND + np.r_[rng.normal(0, 0.015), 0, rng.normal(0, 0.015)]
        return F.stem(top, ctrl, end, radius=0.006, n=70, color=STEM_GREEN)

    # --- flower heads: an even spray on a domed cap, gently irregular -------
    n_heads = 19
    spots = []
    for i in range(n_heads):
        f = (i + 0.5) / n_heads
        psi = np.radians(76) * np.sqrt(f) + rng.normal(0, 0.035)
        az = i * F.GOLDEN + rng.normal(0, 0.08)
        spots.append((f, psi, az, cap_point(psi, az, SPRAY_R + rng.uniform(-0.025, 0.025))))

    # Deal out flower kinds so neighbours never share a colour family.
    pool = (KINDS * 3)[:n_heads - 1]
    rng.shuffle(pool)
    kinds = ['red']                                   # focal rose at the crown
    for f, psi, az, pos in spots[1:]:
        near = {FAMILY[kinds[j]] for j, s in enumerate(spots[:len(kinds)])
                if np.linalg.norm(s[3] - pos) < 0.48}
        pick = next((k for k in pool if FAMILY[k] not in near), pool[0])
        pool.remove(pick)
        kinds.append(pick)

    heads, bloom_c, bloom_a, bloom_delay = [], [], [], []
    for i, ((f, psi, az, pos), kind) in enumerate(zip(spots, kinds)):
        axis = F.normalize(pos - SPRAY_C + np.array([0, 0.3, 0]))
        R = F.frame(axis, twist=rng.uniform(0, F.TAU))
        s = 1.15 if i == 0 else 1.05 - 0.25 * f + rng.uniform(-0.06, 0.06)
        head = _head(kind, rng, s=s).transformed(R, pos)
        head.bid[:] = i
        add(F.Part.concat([head, stem_to_bind(pos)]))
        heads.append(pos)
        bloom_c.append(pos)
        bloom_a.append(axis)
        bloom_delay.append(0.3)                    # every head opens together
    heads = np.array(heads)

    def gap_spots(count, min_head, min_self, psi_max=80):
        """Points on the cap that sit between heads rather than on them."""
        found = []
        for i in range(400):
            f = (i + 0.5) / 400
            psi = np.radians(psi_max) * np.sqrt(f)
            az = i * F.GOLDEN * 1.7
            p = cap_point(psi, az, SPRAY_R - 0.04)
            if np.min(np.linalg.norm(heads - p, axis=1)) < min_head:
                continue
            if found and np.min(np.linalg.norm(np.array(found) - p, axis=1)) < min_self:
                continue
            found.append(p)
        idx = rng.permutation(len(found))[:count]
        return [found[j] for j in idx]

    # --- lavender spikes and baby's breath tucked into the gaps -------------
    for pos in gap_spots(6, 0.17, 0.3):
        R = F.frame(pos - SPRAY_C + np.array([0, 0.5, 0]), twist=rng.uniform(0, F.TAU))
        lav = F.lavender(length=rng.uniform(0.24, 0.3),
                         color=np.array(PURPLE) * rng.uniform(0.85, 1.05), rng=rng)
        add(F.Part.concat([lav.transformed(R, pos), stem_to_bind(pos)]), sway=1.4)
    for pos in gap_spots(8, 0.16, 0.2):
        R = F.frame(pos - SPRAY_C, twist=rng.uniform(0, F.TAU))
        add(F.sprig(rng=rng, n_heads=6, spread=0.06).transformed(R, pos), sway=1.3)

    # --- leaves: a full skirt under the flowers, sloping down and out --------
    n_leaves = 40
    for k in range(n_leaves):
        az = k * F.GOLDEN * 2 + rng.uniform(-0.15, 0.15)
        tier = k % 3
        y = BIND[1] + 0.34 + 0.14 * tier + rng.uniform(-0.04, 0.04)
        rad = 0.05 + 0.12 * tier
        base = np.array([rad * np.cos(az), y, rad * np.sin(az)])
        dirn = np.array([np.cos(az), rng.uniform(0.1, 0.45) + 0.08 * tier, np.sin(az)])
        add(F.leaf(base, dirn, length=rng.uniform(0.42, 0.56),
                   width=rng.uniform(0.1, 0.14), droop=rng.uniform(0.4, 0.65),
                   color=LEAF_GREENS[k % 4], twist=rng.uniform(-0.5, 0.5)),
            sway=0.7)

    # --- stem bundle below the tie, and the ribbon -------------------------
    for dx, dz in rng.normal(0, 0.02, (16, 2)):
        top = BIND + np.r_[dx, 0.02, dz]
        bot = np.array([dx * 2.2, STEM_BOTTOM + rng.uniform(0, 0.06), dz * 2.2])
        p = F.stem(top, (top + bot) / 2, bot, radius=0.006, n=80, color=STEM_GREEN)
        add(p, sway=0.0)
    add(F.ribbon(y_top=BIND[1] + 0.03, y_bot=BIND[1] - 0.2, radius=0.055), sway=0.0)

    b = F.Part.concat(parts)
    ymin, ymax = b.pos[:, 1].min(), b.pos[:, 1].max()
    shift = np.array([0, (ymin + ymax) / 2, 0], np.float32)
    b.pos -= shift
    b.bloom_c = (np.array(bloom_c) - shift).astype(np.float32)
    b.bloom_a = np.array(bloom_a, np.float32)
    b.bloom_delay = np.array(bloom_delay, np.float32)
    b.anchors = b.bloom_c + b.bloom_a * 0.05      # where loose petals come from
    return b
