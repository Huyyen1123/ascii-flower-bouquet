# Background music

Put the site's song here as `song.mp3` (this exact name). Use only a track
you have permission to distribute: it is published with the site.

The page loads it from `audio/song.mp3`. When a visitor taps
"Open your flowers" or "Play song" it fades in over 2 seconds and loops.
If the file is missing, the player shows a message and the flowers play
without music.

To add it:

    cp path/to/your-song.mp3 docs/audio/song.mp3
    git add docs/audio/song.mp3
    git commit -m "Add background music"
    git push
