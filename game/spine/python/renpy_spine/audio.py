"""Dispatch Spine audio events during interactions, outside the renderer."""
import posixpath

import renpy.exports as exports
from renpy.audio import music


def play_events(actor, folder, channel="spine_voice"):
    """Consume events and play audio paths, ignoring duplicate Talk markers."""
    played = []
    for event in actor.events():
        if event["type"] != 5 or not event["audio"]:
            continue
        name = event["audio"].replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/") or ":" in name:
            raise ValueError("Spine audio path must stay within its asset folder")
        path = posixpath.join(folder, name)
        if not exports.loadable(path):
            raise FileNotFoundError("Missing Spine voice: " + path)
        music.set_pan(max(-1.0, min(1.0, event["balance"])), delay=0, channel=channel)
        music.play(path, channel=channel, loop=False, fadeout=0,
                         relative_volume=max(0.0, event["volume"]))
        played.append(path)
    if played and actor.control.paused:
        music.set_pause(True, channel=channel)
    return played
