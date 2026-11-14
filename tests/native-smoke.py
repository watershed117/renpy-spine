"""Exercise the built bridge with original geometric data, without Ren'Py."""
import argparse
import ctypes as C
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'game/python-packages'))
from renpy_spine.native import Native, load_library


def vertices(actor):
    result = []
    for batch in actor.draw():
        assert batch.vertices > 0
        assert all(batch.triangles[i] < batch.vertices for i in range(batch.indices))
        result.extend(batch.xy[i] for i in range(batch.vertices * 2))
    assert result and all(math.isfinite(value) for value in result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, default=ROOT / 'game/spine/native/windows-x86_64/renpy_spine_v1c.dll')
    args = parser.parse_args()
    sample = ROOT / 'examples/game/spine/assets/adapter_sample/sample'
    lib = load_library(args.library)
    atlas = sample.with_suffix('.atlas').read_bytes()
    skeleton = sample.with_suffix('.json').read_bytes()
    actor = Native(lib, atlas, skeleton, is_json=True)
    restored = Native(lib, atlas, skeleton, is_json=True)
    try:
        actor.play('idle')
        first = vertices(actor)
        actor.update(0.35)
        assert max(abs(a-b) for a,b in zip(first, vertices(actor))) > 0.1
        actor.play('touch', track=3, loop=False)
        actor.play('touch_end', track=3, loop=False, queued=True, delay=0.5)
        actor.update(0.27)
        events = actor.events()
        assert any(event['type'] == 5 and event['name'] == 'tap' for event in events), events
        restored.restore(actor.snapshot())
        worst = 0.0
        for _ in range(120):
            actor.update(1/60)
            restored.update(1/60)
            expected, actual = vertices(actor), vertices(restored)
            assert len(expected) == len(actual)
            worst = max(worst, max(abs(a-b) for a,b in zip(expected, actual)))
        assert worst < 0.001, worst
        actor.override('pointer', x=17.0, y=-9.0)
        actor.update(0)
        assert abs(actor.bone('pointer')['x'] - 17) < 1e-5
        matrix = actor.bone_matrix('pointer')
        assert all(math.isfinite(value) for value in matrix)
        actor.override('pointer')
        actor.update(0)
        assert abs(actor.bone('pointer')['x']) < 1e-5
        print(json.dumps({'passed': True, 'frames': 120, 'snapshot_max_xy_error': worst,
            'animations': actor.animations, 'bones': actor.bones, 'event': 'tap'}, indent=2))
    finally:
        actor.close()
        restored.close()


if __name__ == '__main__':
    main()
