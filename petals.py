"""Loose petals that detach from the bouquet and drift around it.

A fixed pool of petal slots is reused forever (no per-frame allocation).
Each slot lives through a sequence of "flights": it detaches from a flower
head, falls slowly on a curved, swirling path around the bouquet, tumbles
and flutters, fades out, and then starts a new flight from another head.

Every flight is a pure function of (slot, flight number), so the system can
also run as an exact loop (``loop=True``) for the pre-rendered web version.

Petals live in world space: the bouquet turns underneath them while they
keep their own motion.  Some swirl with the rotation, some against it, and
because their orbit crosses in front of and behind the bouquet they pass on
both sides of it; the shared Z-buffer sorts out what covers what.
"""

import numpy as np

import flowers as F

COLORS = np.array([
    (0.62, 0.02, 0.08),     # deep red
    (0.95, 0.08, 0.14),     # bright red
    (1.0, 0.55, 0.72),      # soft pink
    (1.0, 0.98, 0.95),      # white
    (1.0, 0.78, 0.86),      # pale pink (occasional)
], np.float32)
COLOR_WEIGHTS = np.array([0.22, 0.28, 0.26, 0.16, 0.08])


class PetalSystem:
    def __init__(self, anchors, count=26, period=15.0, loop=False, seed=5,
                 floor=-1.05):
        self.anchors = np.asarray(anchors, np.float32)
        self.n = count
        self.period = period
        self.loop = loop
        self.seed = seed
        self.floor = floor
        tpl, ch = F.petal_template()
        self.tpl = tpl.astype(np.float32)
        self.tpl_ch = ch
        self.m = len(tpl)
        # In loop mode every flight lasts period / 2, so the pattern repeats.
        self.cycles = 2
        rng = np.random.default_rng(seed)
        self.offset = rng.uniform(0, 1, count)       # stagger slot starts
        # Per-slot flight parameters, refreshed in place when a flight ends.
        self.key = np.full(count, np.iinfo(np.int64).min, np.int64)   # "no flight yet"
        self.life = np.zeros(count)
        self.origin = np.zeros((count, 3))
        self.omega = np.zeros(count)
        self.fall = np.zeros(count)
        self.drift_out = np.zeros(count)
        self.wind_a = np.zeros(count)
        self.wind_f = np.zeros(count)
        self.phase = np.zeros(count)
        self.axis = np.zeros((count, 3))
        self.spin = np.zeros(count)
        self.col = np.zeros((count, 3), np.float32)
        self.scale = np.ones(count)
        # Preallocated output buffers.
        self._pos = np.zeros((count, self.m, 3), np.float32)
        self._nrm = np.zeros((count, self.m, 3), np.float32)
        self._col = np.zeros((count, self.m, 3), np.float32)
        self._ch = np.tile(ch, count).astype(np.uint8)
        self._birth = np.zeros(count)

    # ------------------------------------------------------------------
    def _flight_len(self):
        return self.period / self.cycles if self.loop else None

    def _respawn(self, i, flight, t_birth):
        key = flight % self.cycles if self.loop else flight
        rng = np.random.default_rng((self.seed, i, key))
        self.key[i] = flight
        self.life[i] = self._flight_len() or rng.uniform(6.5, 10.0)
        # Detach from a head, at the bouquet's orientation at birth time.
        a = self.anchors[rng.integers(len(self.anchors))]
        a = a + rng.normal(0, 0.03, 3)
        ang = F.TAU * t_birth / self.period
        c, s = np.cos(ang), np.sin(ang)
        self.origin[i] = (c * a[0] + s * a[2], a[1], -s * a[0] + c * a[2])
        # Bouquet turns at -2pi/period in azimuth; most petals follow it.
        base = -F.TAU / self.period
        self.omega[i] = base * rng.uniform(0.3, 1.6) * rng.choice([1, 1, 1, -0.6])
        self.fall[i] = rng.uniform(0.05, 0.13)
        self.drift_out[i] = rng.uniform(0.03, 0.09)
        self.wind_a[i] = rng.uniform(0.02, 0.07)
        self.wind_f[i] = rng.uniform(0.6, 1.4)
        self.phase[i] = rng.uniform(0, F.TAU)
        self.axis[i] = F.normalize(rng.normal(size=3))
        self.spin[i] = rng.uniform(1.2, 3.2) * rng.choice([-1, 1])
        self.col[i] = COLORS[rng.choice(len(COLORS), p=COLOR_WEIGHTS)] * rng.uniform(0.85, 1.0)
        self.scale[i] = rng.uniform(0.8, 1.2)

    def _flight(self, i, t):
        """Which flight slot i is on at time t, and when it started."""
        if self.loop:
            L = self._flight_len()
            start = self.offset[i] * L
            k = int(np.floor((t - start) / L))
            return k, start + k * L
        # Free-running: flights chain one after another with their own lengths.
        if self.key[i] == np.iinfo(np.int64).min:
            self._birth[i] = -8.0 * self.offset[i]      # some petals already aloft
            self._respawn(i, 0, self._birth[i])
        while t - self._birth[i] > self.life[i]:
            self._birth[i] += self.life[i]
            self._respawn(i, self.key[i] + 1, self._birth[i])
        return self.key[i], self._birth[i]

    # ------------------------------------------------------------------
    def state(self, t):
        """World-space petal points at time t: pos, nrm, rgb, glyph, alpha."""
        ages = np.zeros(self.n)
        for i in range(self.n):
            k, birth = self._flight(i, t)
            if self.loop and self.key[i] != k:
                self._respawn(i, k, birth)
            ages[i] = t - birth
        a = ages
        o = self.origin
        r0 = np.hypot(o[:, 0], o[:, 2]) + 0.04
        th0 = np.arctan2(o[:, 2], o[:, 0])
        th = th0 + self.omega * a + 0.25 * np.sin(0.5 * a + self.phase)  # curved swirl
        r = r0 + self.drift_out * a + 0.03 * np.sin(0.9 * a + self.phase)
        y = o[:, 1] - self.fall * a - 0.004 * a ** 2 + 0.03 * np.sin(1.7 * a + self.phase)
        wx = self.wind_a * np.sin(self.wind_f * a + self.phase)
        wz = self.wind_a * 0.6 * np.cos(self.wind_f * 1.3 * a + self.phase)
        centre = np.stack([r * np.cos(th) + wx, y, r * np.sin(th) + wz], -1)

        # Tumble: rotate the template about each slot's axis (Rodrigues).
        ang = self.spin * a + 0.6 * np.sin(2.1 * a + self.phase)       # flutter
        k = self.axis
        c, s = np.cos(ang)[:, None, None], np.sin(ang)[:, None, None]
        K = np.zeros((self.n, 3, 3))
        K[:, 0, 1], K[:, 0, 2] = -k[:, 2], k[:, 1]
        K[:, 1, 0], K[:, 1, 2] = k[:, 2], -k[:, 0]
        K[:, 2, 0], K[:, 2, 1] = -k[:, 1], k[:, 0]
        R = np.eye(3)[None] + s * K + (1 - c) * (K @ K)
        grow = 0.35 + 0.65 * np.clip(a / 0.9, 0, 1)          # unfurls as it detaches
        tpl = self.tpl[None] * (self.scale * grow)[:, None, None]
        np.einsum('nij,nmj->nmi', R, tpl, out=self._pos, casting='unsafe')
        self._pos += centre[:, None, :]
        up = np.broadcast_to(np.array([0, 1.0, 0]), (self.n, 3))
        nrm = np.einsum('nij,nj->ni', R, up)
        self._nrm[:] = nrm[:, None, :]

        # Fade in after detaching, fade out late in the flight or near the floor.
        life = self.life
        alpha = np.clip((life - a) / (0.35 * life), 0, 1)
        alpha *= np.clip((y - self.floor) / 0.25, 0, 1)
        self._col[:] = (self.col * alpha[:, None])[:, None, :]
        al = np.repeat(alpha, self.m)
        ch = self._ch.copy()
        ch[al < 0.45] = F.ci('.')
        return (self._pos.reshape(-1, 3), self._nrm.reshape(-1, 3),
                self._col.reshape(-1, 3), ch, al)
