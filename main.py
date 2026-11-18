#!/usr/bin/env python3
"""Rotating 3D ASCII flower bouquet for the terminal.

Run:  python3 main.py            (Ctrl+C to quit)
      python3 main.py --fps 60 --period 15
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time

import bouquet

HERE = os.path.dirname(os.path.abspath(__file__))
SONG = os.path.join(HERE, 'web', 'ribs.mp3')
from petals import PetalSystem
from renderer import BG, Renderer

ENTER = '\x1b[?1049h\x1b[?25l\x1b[?7l'          # alt screen, hide cursor, no wrap
LEAVE = '\x1b[0m\x1b[2J\x1b[H\x1b[?7h\x1b[?25h\x1b[?1049l'
SYNC_ON, SYNC_OFF = '\x1b[?2026h', '\x1b[?2026l'  # atomic frame updates


def term_size():
    sz = shutil.get_terminal_size((100, 40))
    return max(sz.columns, 20), max(sz.lines - 1, 10)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fps', type=float, default=30, help='target frame rate (default 30)')
    ap.add_argument('--period', type=float, default=15,
                    help='seconds per full rotation (default 15)')
    ap.add_argument('--seed', type=int, default=7, help='bouquet arrangement seed')
    ap.add_argument('--petals', type=int, default=26, help='number of drifting petals')
    ap.add_argument('--no-petals', action='store_true', help='turn the falling petals off')
    ap.add_argument('--no-bloom', action='store_true',
                    help='start with every flower already open')
    ap.add_argument('--music', default=SONG,
                    help='audio file to play 1 s after start (default: web/ribs.mp3)')
    ap.add_argument('--no-music', action='store_true', help='run silently')
    ap.add_argument('--frames', type=int, default=0,
                    help='stop after N frames (0 = run forever)')
    args = ap.parse_args()

    if not sys.stdout.isatty():
        sys.exit('Please run this in an interactive terminal.')

    cloud = bouquet.build(seed=args.seed)
    petals = None if args.no_petals else PetalSystem(cloud.anchors, count=args.petals,
                                                     period=args.period)
    renderer = Renderer(cloud, period=args.period, petals=petals,
                        bloom=not args.no_bloom)
    out = sys.stdout
    raw = sys.stdout.buffer
    fd = sys.stdin.fileno() if sys.stdin.isatty() else None

    # Stop typed keys from echoing over the animation.
    old_attrs = None
    if fd is not None:
        try:
            import termios
            old_attrs = termios.tcgetattr(fd)
            new = termios.tcgetattr(fd)
            new[3] &= ~(termios.ECHO | termios.ICANON)
            termios.tcsetattr(fd, termios.TCSANOW, new)
        except Exception:
            old_attrs = None

    def restore():
        out.write(LEAVE)
        out.flush()
        if old_attrs is not None:
            import termios
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)

    def on_term(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_term)

    bg = '\x1b[48;2;%d;%d;%dm' % BG
    out.write(ENTER + bg + '\x1b[2J')
    out.flush()

    # Music: macOS afplay, started 1 s in, stopped on exit.
    music_at, music = None, None
    if not args.no_music and os.path.isfile(args.music) and shutil.which('afplay'):
        music_at = 1.0

    frame_dt = 1.0 / args.fps
    size = None
    start = time.perf_counter()
    n = 0
    try:
        while True:
            tick = time.perf_counter()
            if music_at is not None and tick - start >= music_at:
                music = subprocess.Popen(['afplay', args.music], stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                music_at = None
            W, H = term_size()
            if (W, H) != size:                     # resized: repaint background once
                size = (W, H)
                out.write(bg + '\x1b[2J')
            frame = renderer.frame(tick - start, W, H)
            out.flush()
            raw.write((SYNC_ON + frame + SYNC_OFF).encode())   # one write per frame
            raw.flush()
            n += 1
            if args.frames and n >= args.frames:
                break
            delay = frame_dt - (time.perf_counter() - tick)
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        if music is not None and music.poll() is None:
            music.terminate()
        restore()
    elapsed = time.perf_counter() - start
    if elapsed > 0 and n > 1:
        print(f'{n} frames, {n / elapsed:.1f} fps average')


if __name__ == '__main__':
    os.environ.setdefault('PYTHONUNBUFFERED', '1')
    main()
