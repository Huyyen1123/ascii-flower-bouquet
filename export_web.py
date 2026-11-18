#!/usr/bin/env python3
"""Pre-render the bouquet into a self-contained local web page.

Writes web/index.html: the bloom plays once (18 s), then a seamless 15 s loop
(rotation, sway and falling petals all repeat exactly). The page plays
web/ribs.mp3 one second after it opens, with play/pause and a
seek bar. Open it with:  open web/index.html

The public site (GitHub Pages) is built with:  python3 export_web.py --out docs/index.html
With no ribs.mp3 beside it, the page hides its music player.
"""

import argparse
import base64
import json
import os
import zlib

import numpy as np

import bouquet
import petals
import renderer
from flowers import CHARS

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, N, P = 150, 78, 300, 15.0
INTRO, NI = 18.0, 360           # bloom section: 18 s at 20 fps


def main():
    ap = argparse.ArgumentParser(description='Render the bouquet into a web page.')
    ap.add_argument('--out', default=os.path.join(HERE, 'web', 'index.html'),
                    help='where to write the page (default: web/index.html)')
    args = ap.parse_args()
    b = bouquet.build()
    r = renderer.Renderer(b, period=P, petals=petals.PetalSystem(b.anchors, period=P, loop=True))
    r.sway_w = (2 * np.pi / P * 3, 2 * np.pi / P * 2)      # sway repeats every 15 s
    # The bloom intro runs INTRO seconds; by then every head is open, so the
    # 15 s that follow repeat seamlessly (rotation, sway, petals all period P).
    times = [INTRO * i / NI for i in range(NI)] + [INTRO + P * i / N for i in range(N)]
    assert r.bloom_state(INTRO).min() > 0.95, 'bloom must finish before the loop'
    pal = {}
    frames = np.zeros((len(times), H * W), np.uint16)
    for i, t in enumerate(times):
        ch, col = r.project(t, W, H)
        ch, col = ch.ravel(), col.ravel()
        on = col >= 0
        idx = np.array([pal.setdefault(int(k), len(pal) + 1) for k in col[on]], np.uint16)
        frames[i, on] = (idx << 4) | ch[on].astype(np.uint16)
    assert len(pal) < 4096, len(pal)
    blob = base64.b64encode(zlib.compress(frames.astype('<u2').tobytes(), 9)).decode()
    palette = ['#%06x' % k for k, _ in sorted(pal.items(), key=lambda kv: kv[1])]
    meta = {'w': W, 'h': H, 'n': N, 'period': P, 'intro': INTRO, 'ni': NI,
            'chars': CHARS, 'palette': palette}
    tpl = open(os.path.join(HERE, 'web', 'template.html')).read()
    body = tpl.replace('__META__', json.dumps(meta)).replace('__BLOB__', blob)
    page = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<style>body{margin:0;font:14px system-ui,sans-serif}</style>\n'
            '</head><body>\n' + body + '\n</body></html>\n')
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'w').write(page)
    print('wrote', out, f'({len(page) / 1e6:.1f} MB)')


if __name__ == '__main__':
    main()
