"""Matching official exports, real native geometry, and exact state restoration.

Run with the Ren'Py Python executable, or any compatible Windows x64 Python.
With RENPY_SPINE_VERIFY=1 the spine-versions command also checks displayables.
"""
import ctypes as C
import hashlib
import json
from pathlib import Path
import pickle
import sys
import time

ROOT = Path(__file__).resolve().parents[1] / 'game'
sys.path.insert(0, str(ROOT / 'python-packages'))
from renpy_spine.native import Native, load_library, skeleton_version, runtime_version


def pose(native):
    result = []
    for batch in native.draw():
        assert 0 <= batch.page < len(native.pages)
        assert batch.blend in range(4)
        xy = batch.xy[:batch.vertices * 2]
        attrs = batch.attributes[:batch.vertices * 9]
        import math
        assert all(math.isfinite(x) for x in xy + attrs)
        assert all(0 <= i < batch.vertices for i in batch.triangles[:batch.indices])
        result.append((batch.page, batch.blend, batch.vertices, batch.indices,
                       C.string_at(batch.xy, batch.vertices * 8),
                       C.string_at(batch.attributes, batch.vertices * 36),
                       C.string_at(batch.triangles, batch.indices * 4)))
    return result


def fixture_check(version, lib, path):
    folder = path.parent
    model = folder.parent.name
    atlas_file = folder / (model + '.atlas')
    if not atlas_file.exists():
        atlas_file = next(p for p in sorted(folder.glob('*.atlas')) if '-pma' not in p.name)
    atlas = atlas_file.read_bytes()
    data = path.read_bytes()
    is_json = path.suffix == '.json'
    assert runtime_version(skeleton_version(data, is_json)) == version
    native = Native(lib, atlas, data, is_json=is_json)
    result = {'export': skeleton_version(data, is_json), 'animations': len(native.animations),
              'frames': 0, 'restore_frames': 0, 'events': 0}
    try:
        meta = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        result['physics_constraints'] = len(meta.get('physics', [])) + sum(
            constraint.get('type') == 'physics' for constraint in meta.get('constraints', []))
        result['sequence_export'] = '"sequence"' in path.with_suffix('.json').read_text(encoding='utf-8')
        skins = meta.get('skins', [])
        skins = list(skins) if isinstance(skins, dict) else [skin['name'] for skin in skins]
        for skin in skins:
            native.skin(skin)
            native.update(0)
            pose(native)
        native.default_mix(0.17)
        names = list(native.animations)
        assert names
        for name in names:
            native.clear()
            native.play(name)
            unique = set()
            for i in range(24):
                native.update(max(native.animations[name], 0.1) / 24)
                p = pose(native)
                unique.add(hashlib.sha256(repr(p).encode()).digest())
                result['events'] += len(native.events())
                result['frames'] += 1
            assert unique
        # A live mixing predecessor, queued transition, additive upper track,
        # empty animation, zero step, and procedural input all enter the save.
        native.clear()
        native.mix(names[0], names[-1], 0.31)
        native.play(names[0])
        for _ in range(13):
            native.update(1 / 60)
            pose(native)
        native.play(names[-1])
        native.play(names[0], queued=True, delay=0.4)
        native.play(names[-1], track=1, alpha=0.4, additive=True)
        native.empty(track=1, mix=0.18, queued=True, delay=0.5)
        native.override(native.bones[0], x=7.5, rotation=3.0)
        native.update(0.037)
        pose(native)
        native.events()
        snapshot = pickle.loads(pickle.dumps(native.snapshot()))
        expected = []
        for i in range(45):
            native.update(0 if i % 9 == 0 else 1 / 60)
            expected.append((pose(native), native.bone_matrix(native.bones[-1]), native.events()))
        start = time.perf_counter()
        native.restore(snapshot)
        result['restore_ms'] = (time.perf_counter() - start) * 1000
        assert native.events() == []
        for i, reference in enumerate(expected):
            native.update(0 if i % 9 == 0 else 1 / 60)
            actual = (pose(native), native.bone_matrix(native.bones[-1]), native.events())
            assert actual == reference, (version, path.name, 'restore', i)
            result['restore_frames'] += 1
        result['snapshot_bytes'] = len(snapshot)
        # Failed load is atomic, and a save cannot be loaded into other assets.
        saved_pose = pose(native)
        for invalid in (b'invalid', snapshot[:-7], b'RSPJ1' + b'0' * 60):
            try:
                native.restore(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid snapshot accepted')
            assert pose(native) == saved_pose
        native.override(native.bones[0])
        native.update(0)
        pose(native)
        return result
    finally:
        native.close()


def run():
    report = {'versions': {}, 'displayables': {}}
    for version in ('4.0', '4.1', '4.2', '4.3'):
        lib = load_library(ROOT / 'spine/native/windows-x86_64' /
                           ('renpy_spine_%s.dll' % version.replace('.', '_')))
        cases = {}
        for path in sorted((ROOT / 'tools/spine/fixtures' / version).glob('*/export/*')):
            if path.suffix in ('.skel', '.json'):
                print(version, path.parent.parent.name, path.name, flush=True)
                cases[str(path.relative_to(ROOT / 'tools/spine/fixtures' / version))] = fixture_check(version, lib, path)
        report['versions'][version] = cases
    # Native version mismatches fail before any binary decoding occurs.
    for version in ('4.0', '4.1', '4.2', '4.3'):
        folder = ROOT / 'tools/spine/fixtures' / version / 'spineboy/export'
        try:
            Native(lib, (folder / 'spineboy.atlas').read_bytes(), (folder / 'spineboy-pro.skel').read_bytes())
        except ValueError:
            assert version != '4.3'
        else:
            assert version == '4.3'
    try:
        import renpy
        active_renpy = hasattr(renpy, 'config') and hasattr(renpy.config, 'gamedir')
    except ImportError:
        active_renpy = False
    if active_renpy:
        from renpy_spine.displayable import Spine
        from renpy.display import im
        from renpy.display.render import Render
        texture = im.unoptimized_texture
        texture_render = im.render_for_texture
        models = renpy.display.render.models
        # Exercise production Mesh2/render construction without requiring GPU
        # texture uploads in the command-line verifier.
        im.unoptimized_texture = lambda displayable: displayable
        im.render_for_texture = lambda texture, width, height, st, at: Render(width, height)
        renpy.display.render.models = True
        try:
            for version in ('3.8', '4.0', '4.1', '4.2', '4.3'):
                path = ('spine/assets/spr/CH0095_spr.skel' if version == '3.8' else
                        'tools/spine/fixtures/%s/spineboy/export/spineboy-pro.skel' % version)
                atlas_path = None if version == '3.8' else path.rsplit('/', 1)[0] + '/spineboy.atlas'
                actor = Spine(path, atlas=atlas_path)
                name = next(iter(actor.animations))
                actor.play(name)
                session = actor._session()
                session.sync(actor, 0)
                session.sync(actor, 0.25)
                actor.render(1920, 1080, 0.25, 0.25)
                before = pose(session.native)
                restored = pickle.loads(pickle.dumps(actor))
                assert pose(restored._session().native) == before
                actor.render(1920, 1080, 0.5, 0.5)
                bone = actor.bones[0]
                actor.set_bone(bone, x=7)
                actor._pointer_bones({bone: {'x': 27}})
                restored_input = pickle.loads(pickle.dumps(actor))
                input_native = restored_input._session().native
                assert input_native.overrides[bone] == {'x': 7}
                input_native.update(0)
                assert abs(input_native.bone(bone)['x'] - 7) < 1e-5
                report['displayables'][version] = {'render_and_pickle': True, 'batches': len(before),
                                                   'transient_input_released_on_restore': True}
        finally:
            im.unoptimized_texture = texture
            im.render_for_texture = texture_render
            renpy.display.render.models = models
    dest = ROOT.parent / 'reports/multiversion-check.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS:', sum(len(cases) for cases in report['versions'].values()), 'official exports', flush=True)
    return False


if __name__ == '__main__':
    run()
