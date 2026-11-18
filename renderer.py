"""3D projection, z-buffered rasterisation and ANSI true-colour output."""

import numpy as np

from flowers import CHARS, TAU

BG = (0, 0, 0)                      # pure black
CSI = '\x1b['


class Renderer:
    def __init__(self, cloud, period=15.0, tilt_deg=14.0, cam_dist=3.4,
                 cell_aspect=2.05, petals=None, bloom=True):
        self.pos = cloud.pos.astype(np.float32)
        self.nrm = cloud.nrm.astype(np.float32)
        self.col = cloud.col.astype(np.float32)
        self.ch = cloud.ch
        self.sway = cloud.sway.astype(np.float32)
        self.phase = cloud.phase.astype(np.float32)
        self.period = period
        self.tilt = np.radians(tilt_deg)
        self.D = cam_dist
        self.aspect = cell_aspect
        self.sway_w = (1.3, 1.1)          # sway angular speeds (rad/s)
        self.petals = petals              # optional PetalSystem (world space)
        self.petal_start = 12.0 if bloom else 0.0  # petals begin once heads open
        # Blooming: per-head centre, axis and start delay.
        self.bloom = bloom and hasattr(cloud, 'bloom_c')
        self.nb = 0                       # flower-head points come first
        if hasattr(cloud, 'bid'):
            # Put every flower-head point first so a frame works on one slice.
            order = np.argsort(cloud.bid < 0, kind='stable')
            for name in ('pos', 'nrm', 'col', 'ch', 'sway', 'phase'):
                setattr(self, name, getattr(self, name)[order])
            bid = cloud.bid[order]
            self.nb = int((bid >= 0).sum())
        if self.bloom:
            self.bmask = slice(0, self.nb)
            self.bid = bid[:self.nb]
            self.bc = cloud.bloom_c
            self.bdelay = cloud.bloom_delay
            self.bphase = np.random.default_rng(1).uniform(0, TAU, len(self.bc))
            # Static decomposition of each head point about its own axis,
            # so a frame only has to recombine it.
            c = self.bc[self.bid]
            a = cloud.bloom_a[self.bid]
            d = self.pos[self.bmask] - c
            h = np.sum(d * a, axis=1, keepdims=True)
            self._b_c, self._b_a = c, a
            self._b_h = h
            self._b_rad = d - h * a
            self._b_r = np.linalg.norm(self._b_rad, axis=1, keepdims=True)
            self._b_col = self.col[self.bmask]
            self._col_buf = self.col.copy()

        r = np.sqrt(self.pos[:, 0] ** 2 + self.pos[:, 2] ** 2)
        self.radius = float(np.percentile(r, 99.7))
        self._measure_extent()

        L = np.array([-0.45, 0.65, -0.62], np.float32)   # light: upper-left-front
        self.light = L / np.linalg.norm(L)
        H = self.light + np.array([0, 0, -1], np.float32)
        self.half = H / np.linalg.norm(H)

        self.chars = np.array(list(CHARS))
        # Each stored glyph has lighter stand-ins used when the point is in
        # shadow, so shading reads through glyph density as well as colour.
        dim = {'*': '+', '%': 'o', 'o': '+', '+': ':', '=': '-', '~': '-',
               ':': '.', '#': '%', '-': '.', "'": '.', '.': '.', ' ': ' ',
               '@': '%'}
        dimmer = {k: ('.' if v not in '.:' else v) for k, v in dim.items()}
        dimmer.update({'%': '+', '#': 'o', '*': ':', 'o': ':', '+': '.', '@': 'o'})
        lut = lambda m: np.array([CHARS.index(m.get(c, c)) for c in CHARS], np.uint8)
        self.dim1, self.dim2 = lut(dim), lut(dimmer)
        self.ramp = np.array([CHARS.index(c) for c in '.:+*o%@'], np.uint8)
        self._esc = {}
        self._size = None

    # ------------------------------------------------------------------
    def _matrix(self, t):
        a = TAU * t / self.period
        c, s = np.cos(a), np.sin(a)
        Ry = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], np.float32)
        ct, st = np.cos(self.tilt), np.sin(self.tilt)
        Rx = np.array([[1, 0, 0], [0, ct, st], [0, -st, ct]], np.float32)
        return Rx @ Ry

    def _measure_extent(self):
        """Project the cloud over a full turn to find its screen extent.

        The bouquet is kept centred on the rotation axis, so the scale only
        needs to fit the widest/tallest pose; it never changes mid-spin.
        """
        sub = self.pos[::7]
        mx = my = 0.0
        for t in np.linspace(0, self.period, 24, endpoint=False):
            Pc = sub @ self._matrix(t).T
            persp = self.D / (Pc[:, 2] + self.D)
            mx = max(mx, float(np.percentile(np.abs(Pc[:, 0] * persp), 99.9)))
            my = max(my, float(np.abs(Pc[:, 1] * persp).max()))
        self.ext_x, self.ext_y = mx, my

    def _fit(self, W, H):
        k_h = (H / 2 - 0.5) / self.ext_y
        k_w = (W / 2 - 1) / (self.ext_x * self.aspect)
        return min(k_h, k_w)

    BLOOM_TIME = 16.0         # seconds for a head to open from bud

    def bloom_state(self, t):
        """Openness of every head at time t: 0 = closed bud, 1 = open.

        Heads open together, then keep a slow,
        slight breathing motion whose period divides the rotation period,
        so the animation stays loopable.
        """
        x = np.clip((t - self.bdelay) / self.BLOOM_TIME, 0, 1)
        opened = x * x * (3 - 2 * x)                               # smoothstep
        breathe = 0.05 * (0.5 - 0.5 * np.cos(TAU * t / self.period + self.bphase))
        return opened * (1 - breathe)

    def _apply_bloom(self, P, col, t):
        hb = self.bloom_state(t)[self.bid][:, None].astype(np.float32)
        # A bud: petals folded up and in, the whole head smaller.
        size = 0.55 + 0.45 * hb
        new = (self._b_rad * (0.3 + 0.7 * hb)
               + self._b_a * (self._b_h * (0.6 + 0.4 * hb) + (1 - hb) * 0.85 * self._b_r))
        P[self.bmask] = self._b_c + new * size
        col = self._col_buf
        col[self.bmask] = self._b_col * (0.65 + 0.35 * hb)   # closed buds sit in shadow
        return P, col

    def project(self, t, W, H):
        """Return (char-index grid, rgb grid) for time t."""
        # Gentle sway: tops of flowers drift a little, each with its own phase.
        sw = self.sway
        dx = 0.018 * sw * np.sin(self.sway_w[0] * t + self.phase)
        dz = 0.014 * sw * np.cos(self.sway_w[1] * t + self.phase * 1.7)
        P = self.pos.copy()
        col = self.col
        if self.bloom:
            P, col = self._apply_bloom(P, col, t)
        P[:, 0] += dx
        P[:, 2] += dz

        M = self._matrix(t)
        Pc = P @ M.T
        Nc = self.nrm @ M.T
        chs = self.ch
        if self.petals is not None:
            # Petals live in world space: only the camera tilt applies.
            ct, st = np.cos(self.tilt), np.sin(self.tilt)
            Rx = np.array([[1, 0, 0], [0, ct, st], [0, -st, ct]], np.float32)
            pp, pn, pc, pch, al = self.petals.state(t)
            fade = np.clip((t - self.petal_start) / 3.0, 0, 1)
            vis = al * fade > 0.08                 # fully faded petals cover nothing
            pp, pn, pch = pp[vis], pn[vis], pch[vis]
            pc = pc[vis] * fade
            Pc = np.concatenate([Pc, pp @ Rx.T])
            Nc = np.concatenate([Nc, pn @ Rx.T])
            col = np.concatenate([col, pc])
            chs = np.concatenate([chs, pch])

        k = self._fit(W, H)
        depth = Pc[:, 2] + self.D
        persp = self.D / depth
        sx = (W / 2 + Pc[:, 0] * persp * k * self.aspect).astype(np.int32)
        sy = (H / 2 - Pc[:, 1] * persp * k).astype(np.int32)
        ok = (sx >= 0) & (sx < W) & (sy >= 0) & (sy < H)
        idx = sy[ok] * W + sx[ok]
        z = depth[ok]

        # Z-buffer: keep only the nearest point that lands in each cell.
        zbuf = np.full(W * H, np.inf, np.float32)
        np.minimum.at(zbuf, idx, z)
        win = z <= zbuf[idx]
        src = np.flatnonzero(ok)[win]
        cell = idx[win]

        # Lighting (two-sided Lambert + Blinn specular + depth cueing).
        n = Nc[src]
        n = n * np.where(n[:, 2:3] > 0, -1.0, 1.0)          # face the camera
        diff = np.clip(n @ self.light, 0, 1)
        spec = np.clip(n @ self.half, 0, 1) ** 24
        cue = np.clip(1.08 - 0.25 * (Pc[src, 2] + self.radius) / (2 * self.radius), 0.7, 1.1)
        shade = np.minimum((0.62 + 0.5 * diff) * cue, 1.0)    # never wash out to white

        # Silhouette outlines: darken a cell when a neighbour is clearly
        # nearer, which inks a thin shadow line around each flower head.
        zb = zbuf.reshape(H, W)
        near = np.full((H, W), np.inf, np.float32)
        near[1:, :] = np.minimum(near[1:, :], zb[:-1, :])
        near[:-1, :] = np.minimum(near[:-1, :], zb[1:, :])
        near[:, 1:] = np.minimum(near[:, 1:], zb[:, :-1])
        near[:, :-1] = np.minimum(near[:, :-1], zb[:, 1:])
        gap = zbuf[cell] - near.ravel()[cell]
        shade = shade * np.where(gap > 0.06, 0.45, 1.0)
        rgb = np.clip(col[src] * shade[:, None] + (0.18 * spec)[:, None], 0, 1)
        rgb = rgb ** 0.78                                     # lift midtones: vivid, not murky
        rgb = (rgb * 255).astype(np.int32)

        chars = np.zeros(W * H, np.uint8)
        colors = np.full(W * H, -1, np.int32)
        g = chs[src]
        lum = shade * col[src].max(axis=1)
        g = np.where(lum < 0.42, self.dim1[g], g)
        g = np.where(lum < 0.22, self.dim2[g], g)
        # Flower heads: glyph follows lit brightness, so each petal's curve
        # and the layering of a rose read through glyph density.
        sh = src < self.nb
        if sh.any():
            level = np.clip((lum[sh] - 0.08) / 0.8, 0, 0.999)
            g[sh] = self.ramp[(level * len(self.ramp)).astype(np.int32)]
        chars[cell] = g
        q = ((rgb >> 4) << 4) | 8                             # 16 levels/channel: fewer escapes
        colors[cell] = (q[:, 0] << 16) | (q[:, 1] << 8) | q[:, 2]
        return chars.reshape(H, W), colors.reshape(H, W)

    # ------------------------------------------------------------------
    def frame(self, t, W, H):
        """Build a full ANSI frame string (cursor-home, no screen clear)."""
        chars, colors = self.project(t, W, H)
        glyph = self.chars[chars]
        esc = self._esc
        out = [CSI + 'H', CSI + '48;2;%d;%d;%dm' % BG]
        for y in range(H):
            row_c = colors[y].tolist()
            row_g = glyph[y].tolist()
            last = -2
            buf = []
            for x in range(W):
                c = row_c[x]
                if c < 0:
                    buf.append(' ')
                    continue
                if c != last:
                    e = esc.get(c)
                    if e is None:
                        e = esc[c] = CSI + '38;2;%d;%d;%dm' % (c >> 16, (c >> 8) & 255, c & 255)
                    buf.append(e)
                    last = c
                buf.append(row_g[x])
            out.append(''.join(buf))
            if y < H - 1:
                out.append('\r\n')
        return ''.join(out)
