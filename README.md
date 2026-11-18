# ASCII Flower Bouquet

A colourful hand-tied bouquet built from 3D math and drawn in ASCII on pure black. Every flower opens from a closed bud at the same moment, then the bouquet turns a full 360° while red, pink and white petals drift, swirl and tumble around it: a rounded spray of roses, daisies, cosmos, asters, sunflowers and lavender over a skirt of bright leaves, with every stem gathered into a long bundle tied with a pink ribbon.

Every flower, leaf, stem and the ribbon is a cloud of sampled 3D points (~195k in total). Each point stores its position, surface normal, colour and ASCII character. Every frame, the renderer:

1. opens every flower from a bud at the same time (petals unfold outward over about 16 s), then lets them breathe very slightly,
2. sways the flower heads a little, each with its own phase,
3. rotates the whole bouquet around the Y axis (one turn per 15 s) and tilts it slightly toward you,
4. adds the drifting petals, which live in world space so they keep their own motion while the bouquet turns,
5. projects the points with perspective onto the terminal grid,
6. resolves what's in front with a Z-buffer, so near flowers cover far ones,
7. lights each point (Lambert + specular + depth cueing), darkens silhouette edges, and swaps shadowed glyphs for lighter ones (`*`→`+`→`:`→`.`); flower heads take their glyph from a brightness ramp (`.` `:` `+` `*` `o` `%` `@`) so petal curves read clearly,
8. writes one ANSI 24-bit-colour frame in place, using cursor-home and synchronized output. The screen is never cleared, so it doesn't flicker.

**Live demo:** https://huyyen1123.github.io/ascii-flower-bouquet/

## Setup

```bash
cd ascii-flower-bouquet
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python3 main.py
```

Press **Ctrl+C** to quit. The cursor and the terminal state are restored.

Options:

| flag | default | meaning |
|------|---------|---------|
| `--fps` | 30 | target frame rate (60 works on most Macs) |
| `--period` | 15 | seconds per full rotation |
| `--seed` | 7 | changes the arrangement |
| `--petals` | 26 | number of drifting petals |
| `--no-petals` | off | turn the falling petals off |
| `--no-bloom` | off | start with every flower already open |
| `--music` | `web/audio/song.mp3` | song to play 1 s after start (macOS `afplay`) |
| `--no-music` | off | run silently |
| `--frames` | 0 | stop after N frames (0 = forever) |

**Tip:** you need a terminal with true colour (VS Code, iTerm2, Ghostty, kitty, WezTerm). macOS Terminal.app only supports true colour from macOS 15 onward. The bouquet scales to the window, so a larger window with a smaller font (⌘− in VS Code / Terminal) shows much finer petal detail.

## Web version

```bash
python3 export_web.py
open web/index.html
```

`export_web.py` pre-renders the animation into a single page, `web/index.html` (the public site is the same page built with `--out docs/index.html`): the bloom plays once (18 s), then the bouquet keeps turning in a seamless 15 s loop with the petals falling. The page opens on the closed buds with an **Open your flowers** button, and has Pause and Replay bloom buttons.

## Deploying

The site is static: `docs/index.html` holds every frame plus the player, so no server or build step is needed.

- **GitHub Pages** serves `docs/` from `main`.
- **Vercel** uses `vercel.json` (no framework, no build, output directory `docs`). `.vercelignore` keeps the Python files out of the upload, so Vercel never tries to run `main.py` as a serverless function.

After changing the bouquet, rebuild the page with `python3 export_web.py --out docs/index.html` and push.

## Music

The web page plays **Ribs by Lorde** through SoundCloud's official embedded player (its compact 20 px version, styled dark to match the page). Nothing is downloaded or rehosted: the page controls SoundCloud's own player through the [Widget API](https://developers.soundcloud.com/docs/api/html5-widget).

- Tapping **Open your flowers** starts the bloom and the song together; **Play our song ♡** plays and pauses it. The song starts over when it ends.
- Phones only allow sound after a tap. If a browser still holds the music back, the page says so and offers SoundCloud's own play button plus a link to the track.
- If SoundCloud can't load at all, the flowers play on with a link to listen on SoundCloud.

The terminal version (`python3 main.py`) can play a local file instead: it plays `web/audio/song.mp3` 1 s after launch (macOS `afplay`), or pass `--music path/to/song.mp3` / `--no-music`. Audio files are never committed.

## Files

| file | contents |
|------|----------|
| `main.py` | entry point, terminal setup/restore, animation loop |
| `flowers.py` | procedural geometry: layered roses (rings of cupped, overlapping petals around a tight bud, with sepals), radial daisy/aster/cosmos/sunflower, lavender spikes, baby's breath, lanceolate leaves with folded midrib and veins, Bezier stems, a ribbon spiralled round the stems with trailing tails |
| `bouquet.py` | places the heads on a domed cap (focal rose at the crown, colours dealt so neighbours differ), tucks lavender and baby's breath into the gaps, runs each stem to the tie point, adds the leaf skirt, stem bundle and ribbon, and records each head's bloom centre and timing |
| `petals.py` | the falling-petal system: a fixed pool of reused petal slots on curved, swirling, tumbling paths that fade out and respawn; can run as an exact 15 s loop |
| `renderer.py` | bloom animation, rotation, perspective projection, Z-buffer, lighting, edge outlines, ANSI frame builder |
| `export_web.py` | renders the bloom and the 15 s loop into `web/index.html` |
| `web/template.html` | the page the frames are played in (canvas player, Open your flowers start, SoundCloud music) |
