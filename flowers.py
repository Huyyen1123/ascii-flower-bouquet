"""Procedural 3D geometry for every element of the bouquet.

Each generator returns a :class:`Part`: a cloud of sampled 3D points where
every point carries a position, a surface normal (for lighting), an RGB
colour and the ASCII character used to draw it.

Flowers are built in a local frame where +Y is the flower's facing axis and
the base of the head sits at the origin.  :func:`frame` builds the rotation
that points that axis anywhere in the bouquet.
"""

import numpy as np

TAU = 2.0 * np.pi
GOLDEN = np.pi * (3.0 - np.sqrt(5.0))

# Every point stores an index into this table.
CHARS = " .:+*o%#=~-'@"
_CI = {c: i for i, c in enumerate(CHARS)}


def ci(c):
    return _CI[c]


# ---------------------------------------------------------------------------
# Point cloud container
# ---------------------------------------------------------------------------
class Part:
    def __init__(self, pos, nrm, col, ch, sway=None):
        self.pos = np.asarray(pos, np.float32).reshape(-1, 3)
        n = len(self.pos)
        self.nrm = np.asarray(nrm, np.float32).reshape(-1, 3)
        self.col = np.broadcast_to(np.asarray(col, np.float32), (n, 3)).copy()
        self.ch = np.broadcast_to(np.asarray(ch, np.uint8), (n,)).copy()
        # Sway: amplitude weight and phase per point (filled in by bouquet).
        self.sway = np.zeros(n, np.float32) if sway is None else sway
        self.phase = np.zeros(n, np.float32)
        self.bid = np.full(n, -1, np.int32)      # flower head index for blooming

    def __len__(self):
        return len(self.pos)

    def transformed(self, R, t=(0, 0, 0)):
        R = np.asarray(R, np.float32)
        p = Part(self.pos @ R.T + np.asarray(t, np.float32), self.nrm @ R.T,
                 self.col, self.ch, self.sway.copy())
        p.phase = self.phase.copy()
        p.bid = self.bid.copy()
        return p

    @staticmethod
    def concat(parts):
        parts = [p for p in parts if len(p)]
        out = Part(np.concatenate([p.pos for p in parts]),
                   np.concatenate([p.nrm for p in parts]),
                   np.concatenate([p.col for p in parts]),
                   np.concatenate([p.ch for p in parts]),
                   np.concatenate([p.sway for p in parts]))
        out.phase = np.concatenate([p.phase for p in parts])
        out.bid = np.concatenate([p.bid for p in parts])
        return out


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------
def normalize(v, axis=-1):
    v = np.asarray(v, np.float64)
    n = np.linalg.norm(v, axis=axis, keepdims=True)
    return v / np.where(n < 1e-9, 1.0, n)


def grid_normals(P):
    """Normals of a parametric surface sampled on a (u, v, 3) grid."""
    du = np.gradient(P, axis=0)
    dv = np.gradient(P, axis=1)
    n = np.cross(du, dv)
    bad = np.linalg.norm(n, axis=-1) < 1e-12
    n[bad] = (0.0, 1.0, 0.0)
    return normalize(n)


def frame(axis, twist=0.0):
    """Rotation matrix mapping local +Y onto ``axis`` (with a twist about it)."""
    a = normalize(axis)
    ref = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 0, 1.0])
    x = normalize(np.cross(a, ref))
    z = np.cross(x, a)
    c, s = np.cos(twist), np.sin(twist)
    x, z = c * x + s * z, -s * x + c * z
    return np.column_stack([x, a, z])


def rot_y(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def lerp(a, b, t):
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    t = np.asarray(t, np.float64)[..., None]
    return a + (b - a) * t


def bezier(p0, p1, p2, t):
    t = np.asarray(t)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


# ---------------------------------------------------------------------------
# Rose: layers of cupped, overlapping petals around a tight bud
# ---------------------------------------------------------------------------
def rose(outer, inner, size=0.16, layers=6, n_u=18, n_v=13, rng=None):
    """A rose built petal by petal.

    Each layer is a ring of broad, cupped petals.  Inner layers are short,
    upright and lean inward to close the bud; outer layers are longer, start
    lower, open outward and roll their tips back.  Neighbouring petals
    overlap by ~35% and every layer is rotated against the last, which gives
    the layered spiral you read as a rose from any side.
    """
    rng = rng or np.random.default_rng()
    outer = np.asarray(outer, np.float64)
    inner = np.asarray(inner, np.float64)
    counts = [3, 4, 5, 5, 6, 7, 8][:layers]
    u = np.linspace(0, 1, n_u)[:, None]
    v = np.linspace(-1, 1, n_v)[None, :]
    du = 1.0 / (n_u - 1)
    parts = []
    for L, k in enumerate(counts):
        o = L / (len(counts) - 1)                            # 0 = bud, 1 = outermost
        length = size * (0.62 + 0.45 * o)
        # Petal profile: lean angle from vertical along the petal.
        # Rounded bowl: outer petals leave the base nearly flat, sweep up,
        # then flare at the lip; inner petals stay upright and lean in.
        alpha = (0.1 + 1.15 * o * (1 - u) ** 2) - 0.35 * (1 - o) * u + 0.85 * o ** 2 * u ** 4
        r = size * (0.03 + 0.2 * o) + np.cumsum(np.sin(alpha), axis=0) * du * length
        h = -size * 0.2 * o + np.cumsum(np.cos(alpha), axis=0) * du * length
        for j in range(k):
            phc = TAU * j / k + L * 0.95 + rng.normal(0, 0.08)
            half = np.pi / k * 1.35
            shape = np.sin(np.pi * np.clip(0.12 + 0.88 * u, 0, 1)) ** 0.55 * (0.75 + 0.25 * u)
            ph = phc + v * half * shape
            cup = size * (0.07 * (1 - o) - 0.05 * o) * v ** 2 * np.sin(np.pi * u) ** 0.5
            rr = r - cup
            P = np.stack([rr * np.cos(ph), np.broadcast_to(h, rr.shape), rr * np.sin(ph)], -1)
            N = grid_normals(P)
            N = N * np.sign(np.sum(N[..., [0, 2]] * P[..., [0, 2]], -1, keepdims=True) + 1e-9)

            U = np.broadcast_to(u, rr.shape)
            V = np.broadcast_to(v, rr.shape)
            base = lerp(inner, outer, 0.25 + 0.75 * o) * rng.uniform(0.9, 1.06)  # petal-to-petal variety
            col = base * (0.6 + 0.4 * U ** 0.7)[..., None]            # shadowed base
            # Each petal is lit in the middle and tucked into shadow where it
            # slides under its neighbours, so individual petals separate.
            col = col * (0.7 + 0.3 * np.cos(np.pi * V / 2) ** 0.8)[..., None]
            rim = np.clip((U - 0.78) / 0.22, 0, 1) + np.clip((np.abs(V) - 0.82) / 0.18, 0, 1)
            rim = np.clip(rim, 0, 1)[..., None]
            col = col * (1 - 0.35 * rim) + np.clip(outer * 1.15 + 0.12, 0, 1) * 0.35 * rim
            ch = np.full(rr.shape, ci('o'), np.uint8)
            ch[U < 0.3] = ci(':')
            ch[(U > 0.82) | (np.abs(V) > 0.85)] = ci('*')
            if o < 0.3:
                ch[U >= 0.3] = ci('@')
            parts.append(Part(P.reshape(-1, 3), N.reshape(-1, 3),
                              np.clip(col, 0, 1).reshape(-1, 3), ch.ravel()))
    # Green sepals peeking out under the outer petals.
    for j in range(5):
        phc = TAU * j / 5 + 0.3
        s = np.linspace(0, 1, 8)[:, None]
        w = np.linspace(-1, 1, 3)[None, :]
        rr = size * (0.15 + 0.55 * s)
        hh = -size * (0.22 + 0.25 * s ** 1.5)
        ph = phc + w * 0.18 * (1 - s)
        P = np.stack([rr * np.cos(ph), np.broadcast_to(hh, ph.shape), rr * np.sin(ph)], -1)
        parts.append(Part(P.reshape(-1, 3), normalize(P.reshape(-1, 3) * [1, -1, 1]),
                          (0.2, 0.55, 0.22), ci('+')))
    return Part.concat(parts)


# ---------------------------------------------------------------------------
# A single loose petal (used by the falling-petal system)
# ---------------------------------------------------------------------------
def petal_template(length=0.034, width=0.024):
    """A small cupped oval in the local XZ plane, centred on the origin."""
    pts, ch = [], []
    for ring, (rf, n, c) in enumerate([(0.0, 1, 'o'), (0.5, 6, 'o'), (1.0, 10, '*')]):
        a = np.linspace(0, TAU, n, endpoint=False) + ring * 0.3
        x = rf * length * 0.5 * np.cos(a)
        z = rf * width * 0.5 * np.sin(a)
        y = 0.35 * (x ** 2 / (length * 0.5) + z ** 2 / (width * 0.5))
        pts.append(np.stack([x, y, z], -1))
        ch += [ci(c)] * n
    return np.concatenate(pts), np.array(ch, np.uint8)


# ---------------------------------------------------------------------------
# Daisy / aster / sunflower: radial petals around a domed centre
# ---------------------------------------------------------------------------
def daisy(petal, center, n_petals=18, radius=0.15, petal_w=0.3, cup=0.25,
          droop=0.35, notch=False, layers=2, n_center=650, rng=None):
    rng = rng or np.random.default_rng()
    parts = []

    # Domed disc florets on a Fibonacci (phyllotaxis) spiral.
    rc = radius * 0.3
    i = np.arange(n_center)
    rr = rc * np.sqrt((i + 0.5) / n_center)
    a = i * GOLDEN
    hh = 0.45 * rc * (1 - (rr / rc) ** 2) + 0.02 * radius
    P = np.stack([rr * np.cos(a), hh, rr * np.sin(a)], -1)
    N = normalize(np.stack([P[:, 0] * 1.6, np.full(n_center, rc), P[:, 2] * 1.6], -1))
    t = rr / rc
    ccol = lerp(np.asarray(center) * 1.15, np.asarray(center) * 0.6, t)
    ch = np.where(i % 3 == 0, ci('o'), np.where(t < 0.35, ci('%'), ci(':')))
    parts.append(Part(P, N, np.clip(ccol, 0, 1), ch))

    # Petals: tapered strips that rise, cup and droop at the tips.
    L = radius - rc * 0.8
    n_s, n_w = 22, 7
    s = np.linspace(0, 1, n_s)[:, None]
    w = np.linspace(-1, 1, n_w)[None, :]
    for layer in range(layers):
        for k in range(n_petals):
            ang = TAU * (k + 0.5 * layer) / n_petals + rng.normal(0, 0.05)
            ln = L * rng.uniform(0.88, 1.05) * (0.9 if layer else 1.0)
            hw = ln * petal_w * np.sin(np.pi * np.clip(s, 0, 1) ** 0.8) ** 0.75
            if notch:                                    # cosmos-style notched tips
                hw = hw * (1 - 0.25 * np.exp(-((s - 1) / 0.08) ** 2))
            radial = rc * 0.75 + ln * s
            lift = ln * (0.25 * s - droop * s ** 2) + 0.012 * layer * radius
            lift = lift + cup * ln * w ** 2 * np.sin(np.pi * s) * 0.3
            lat = w * hw
            ca, sa = np.cos(ang), np.sin(ang)
            Pp = np.stack([radial * ca - lat * sa,
                           np.broadcast_to(lift, lat.shape),
                           radial * sa + lat * ca], -1)
            Np = grid_normals(Pp)
            Np[Np[..., 1] < 0] *= -1
            shade = 0.82 + 0.18 * np.cos(np.pi * w)               # midrib groove
            pc = np.asarray(petal)[None, None, :] * shade[..., None]
            pc = pc * (0.72 + 0.28 * np.clip(s * 2.5, 0, 1))[..., None]
            if layer:
                pc = pc * 0.85
            pch = np.full(lat.shape, ci('*'), np.uint8)
            pch[np.abs(np.broadcast_to(w, lat.shape)) < 0.35] = ci('o')
            pch[np.broadcast_to(s, lat.shape) < 0.18] = ci(':')
            parts.append(Part(Pp.reshape(-1, 3), Np.reshape(-1, 3),
                              np.clip(pc, 0, 1).reshape(-1, 3), pch.ravel()))
    return Part.concat(parts)


# ---------------------------------------------------------------------------
# Lavender: a spike of tiny florets whorled up a tapering stalk
# ---------------------------------------------------------------------------
def lavender(length=0.34, color=(0.62, 0.36, 0.9), rng=None):
    rng = rng or np.random.default_rng()
    parts = []
    n_whorl = 34
    pts, nrms, cols, chs = [], [], [], []
    for j in range(n_whorl):
        s = j / (n_whorl - 1)
        y = length * s
        bend = 0.06 * length * s ** 2                        # spike nods over
        spread = 0.028 * (1 - 0.65 * s) + 0.004
        rf = 0.014 * (1 - 0.55 * s) + 0.004
        for k in range(5):
            a = TAU * k / 5 + j * 0.9
            c = np.array([spread * np.cos(a) + bend, y, spread * np.sin(a)])
            # tiny floret: a small sphere sampled with a Fibonacci lattice
            m = 18
            i = np.arange(m)
            zz = 1 - 2 * (i + 0.5) / m
            rr = np.sqrt(1 - zz ** 2)
            th = i * GOLDEN
            d = np.stack([rr * np.cos(th), zz, rr * np.sin(th)], -1)
            pts.append(c + d * rf * rng.uniform(0.8, 1.2))
            nrms.append(normalize(d + np.array([np.cos(a), 0, np.sin(a)])))
            tint = rng.uniform(0.75, 1.15)
            base = np.asarray(color) * tint
            if s > 0.85:
                base = base * 0.8 + np.array([0.25, 0.15, 0.35]) * 0.2
            cols.append(np.broadcast_to(base, (m, 3)))
            ch = np.where(i % 4 == 0, ci('*'), np.where(i % 2, ci('o'), ci(':')))
            chs.append(ch)
    parts.append(Part(np.concatenate(pts), np.concatenate(nrms),
                      np.clip(np.concatenate(cols), 0, 1), np.concatenate(chs)))
    parts.append(stem(np.zeros(3), np.array([0, length * 0.5, 0]),
                      np.array([0.06 * length, length, 0]), radius=0.005, n=40))
    return Part.concat(parts)


# ---------------------------------------------------------------------------
# Baby's breath / small filler sprays
# ---------------------------------------------------------------------------
def sprig(color=(0.97, 0.95, 1.0), n_heads=16, spread=0.09, rng=None):
    rng = rng or np.random.default_rng()
    parts = []
    for _ in range(n_heads):
        d = normalize(np.array([rng.normal(0, 0.6), 1.0, rng.normal(0, 0.6)]))
        tip = d * spread * rng.uniform(0.5, 1.0)
        parts.append(stem(np.zeros(3), tip * 0.5 + np.array([0, 0.01, 0]), tip,
                          radius=0.0025, n=12, color=(0.35, 0.55, 0.3)))
        m = 26
        i = np.arange(m)
        zz = 1 - 2 * (i + 0.5) / m
        rr = np.sqrt(1 - zz ** 2)
        th = i * GOLDEN
        dd = np.stack([rr * np.cos(th), zz, rr * np.sin(th)], -1)
        r = 0.012 * rng.uniform(0.7, 1.2)
        tint = np.asarray(color) * rng.uniform(0.85, 1.0)
        ch = np.where(i % 3 == 0, ci('*'), np.where(i % 3 == 1, ci('.'), ci('o')))
        parts.append(Part(tip + dd * r, dd, tint, ch))
    return Part.concat(parts)


# ---------------------------------------------------------------------------
# Leaves: curved blades with pointed tips, a folded midrib and veins
# ---------------------------------------------------------------------------
def leaf(base, direction, length=0.36, width=0.075, droop=0.45, fold=0.35,
         color=(0.18, 0.55, 0.2), twist=0.0, n_s=64, n_w=13):
    d = normalize(direction)
    down = np.array([0, -1.0, 0]) - np.dot([0, -1.0, 0], d) * d
    g = normalize(down if np.linalg.norm(down) > 1e-3 else np.array([1.0, 0, 0]))
    side = np.cross(d, g)
    c, s_ = np.cos(twist), np.sin(twist)
    g, side = c * g + s_ * side, -s_ * g + c * side

    s = np.linspace(0, 1, n_s)[:, None]
    w = np.linspace(-1, 1, n_w)[None, :]
    # Lanceolate outline: narrow petiole, widest ~35%, sharp pointed tip.
    hw = width * (s ** 0.55) * (1 - s) ** 0.9 * 2.1
    lat = w * hw
    along = length * s
    bend = droop * length * s ** 2                       # arches over / down
    vfold = -fold * np.abs(lat)                          # V-shaped midrib fold
    wave = 0.12 * hw * np.sin(s * 22 + w * 2)            # gently rippled edge
    P = (np.asarray(base)[None, None, :]
         + along[..., None] * d + (bend + vfold + wave * np.abs(w))[..., None] * g
         + lat[..., None] * side)
    N = grid_normals(P)

    S = np.broadcast_to(s, lat.shape)
    W = np.broadcast_to(w, lat.shape)
    col = np.asarray(color)[None, None, :] * (0.75 + 0.35 * S[..., None] * (1 - S[..., None]) * 2)
    rib = np.abs(W) < 0.1
    vein = (np.abs(np.sin((S * 9 - np.abs(W) * 1.4) * np.pi)) < 0.18) & ~rib
    col[rib] = col[rib] * 0.65 + np.array([0.7, 0.85, 0.45]) * 0.35
    col[vein] *= 1.18
    edge = np.abs(W) > 0.85
    col[edge] *= 0.9
    ch = np.full(lat.shape, ci('='), np.uint8)
    ch[vein] = ci('-')
    ch[rib] = ci(':')
    ch[edge] = ci('=')
    return Part(P.reshape(-1, 3), N.reshape(-1, 3),
                np.clip(col, 0, 1).reshape(-1, 3), ch.ravel())


# ---------------------------------------------------------------------------
# Stems: thin tubes along a quadratic Bezier
# ---------------------------------------------------------------------------
def stem(p0, p1, p2, radius=0.008, n=60, k=6, color=(0.25, 0.5, 0.18)):
    t = np.linspace(0, 1, n)
    C = bezier(np.asarray(p0), np.asarray(p1), np.asarray(p2), t)
    T = normalize(np.gradient(C, axis=0))
    ref = np.where(np.abs(T[:, 1:2]) < 0.9, [[0, 1.0, 0]], [[1.0, 0, 0]])
    U = normalize(np.cross(T, ref))
    V = np.cross(T, U)
    a = np.linspace(0, TAU, k, endpoint=False)
    ring = (np.cos(a)[None, :, None] * U[:, None, :]
            + np.sin(a)[None, :, None] * V[:, None, :])
    P = C[:, None, :] + radius * ring
    shade = 0.85 + 0.15 * np.cos(a)[None, :]
    col = np.asarray(color)[None, None, :] * shade[..., None] * np.ones((n, 1, 1))
    ch = np.where(np.arange(n)[:, None] % 4 == 0, ci('+'), ci(':')) * np.ones((1, k), int)
    return Part(P.reshape(-1, 3), ring.reshape(-1, 3), col.reshape(-1, 3),
                ch.astype(np.uint8).ravel())


# ---------------------------------------------------------------------------
# Ribbon: a band spiralled round the stem bundle, with two trailing tails
# ---------------------------------------------------------------------------
def ribbon(y_top=-0.9, y_bot=-1.12, radius=0.07, turns=3.0,
           color=(1.0, 0.35, 0.65), width=0.045):
    parts = []
    # Spiral band
    u = np.linspace(0, 1, 420)[:, None]
    w = np.linspace(-1, 1, 7)[None, :]
    a = TAU * turns * u
    y = y_top + (y_bot - y_top) * u + w * width * 0.5
    r = radius * (1 + 0.15 * np.cos(a * 0.5)) + 0.004 * w ** 2
    P = np.stack([r * np.cos(a) * np.ones_like(w), y, r * np.sin(a) * np.ones_like(w)], -1)
    N = normalize(np.stack([np.cos(a) * np.ones_like(w), 0.15 * np.ones_like(y),
                            np.sin(a) * np.ones_like(w)], -1))
    shade = 0.8 + 0.2 * np.cos(np.pi * w)
    col = np.asarray(color) * shade[..., None] * np.ones_like(u)[..., None]
    W = np.broadcast_to(w, y.shape)
    ch = np.where(np.abs(W) > 0.7, ci('-'), ci('='))
    parts.append(Part(P.reshape(-1, 3), N.reshape(-1, 3), col.reshape(-1, 3),
                      ch.astype(np.uint8).ravel()))

    # Knot and two loose tails that flutter down and outward
    knot = np.array([0.0, y_top, -radius * 1.1])
    for sgn in (-1, 1):
        s = np.linspace(0, 1, 120)[:, None]
        w = np.linspace(-1, 1, 6)[None, :]
        cx = sgn * (0.03 + 0.2 * s) + 0.03 * np.sin(s * 8) * sgn
        cy = -0.42 * s
        cz = -0.03 * s + 0.02 * np.sin(s * 10 + sgn)
        P = (knot + np.stack([cx + w * 0.022, cy + w * 0.012, cz + 0 * w], -1))
        N = grid_normals(P)
        N[N[..., 2] > 0] *= -1
        col = np.asarray(color) * (0.85 + 0.15 * np.cos(np.pi * w))[..., None] * np.ones_like(s)[..., None]
        ch = np.where(np.abs(np.broadcast_to(w, P.shape[:2])) > 0.7, ci('-'), ci('='))
        parts.append(Part(P.reshape(-1, 3), N.reshape(-1, 3), col.reshape(-1, 3),
                          ch.astype(np.uint8).ravel()))
    i = np.arange(160)
    zz = 1 - 2 * (i + 0.5) / 160
    rq = np.sqrt(1 - zz ** 2)
    d = np.stack([rq * np.cos(i * GOLDEN), zz, rq * np.sin(i * GOLDEN)], -1)
    parts.append(Part(knot + d * np.array([0.035, 0.025, 0.025]), d,
                      np.asarray(color) * 0.95, ci('o')))
    return Part.concat(parts)
