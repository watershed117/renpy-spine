"""Verify released plugin imports and five-version rendering in real Ren'Py.

Run with the SDK's bundled Python and --renpy-sdk <SDK directory>, after
building the release ZIPs and fetching the official fixtures. Textures use
Render placeholders; this checks imports and Mesh2, not GPU output.
"""
import argparse
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import sys
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]


def archive_modules(game):
    # RPA 3.0 index format used by the SDK's launcher/game/archiver.rpy.
    index = {}
    with (game / 'spine_test.rpa').open('wb') as output:
        output.write(b'RPA-3.0 0000000000000000 00000000\n')
        files = sorted((game / 'spine/python').rglob('*.py'))
        files += sorted((game / 'spine/assets').rglob('*'))
        for filename in files:
            if not filename.is_file():
                continue
            data = filename.read_bytes()
            index[filename.relative_to(game).as_posix()] = [(output.tell(), len(data), b'')]
            output.write(data)
            filename.unlink()
        offset = output.tell()
        output.write(zlib.compress(pickle.dumps(index, protocol=2)))
        output.seek(0)
        output.write(f'RPA-3.0 {offset:016x} 00000000\n'.encode())


CHECK = '''init python:
    def _spine_directory_check():
        import pickle
        import existing_dependency
        import renpy_spine.displayable as displayable
        from renpy.display.render import Render
        import renpy.display.render as renderer
        import renpy.display.im as images
        assert existing_dependency.marker == 117
        assert not displayable._libraries, "Example must not create an actor during initialization"
        assert renpy.has_label("start") and renpy.has_label("renpy_spine_example")
        assert displayable.Spine.__module__ == "renpy_spine.displayable"
        renderer.models = True
        images.render_for_texture = lambda texture, width, height, st, at: Render(width, height)
        for version in ("3.8", "4.0", "4.1", "4.2", "4.3"):
            if version == "3.8":
                skeleton = "spine/assets/adapter_sample/sample.json"
                atlas = None
                animation = "idle"
            else:
                skeleton = "spine/assets/check/" + version + "/spineboy-pro.skel"
                atlas = "spine/assets/check/" + version + "/spineboy.atlas"
                animation = "walk"
            actor = displayable.Spine(skeleton, atlas=atlas, animation=animation)
            actor.render(960, 540, 0, 0)
            actor.render(960, 540, 0.2, 0.2)
            restored = pickle.loads(pickle.dumps(actor))
            restored.render(960, 540, 0.2, 0.2)
            assert restored.stats["vertices"] > 0
            print("SPINE INSTALL PASS", version, restored.stats["vertices"])
        return False
    from renpy import arguments as _spine_check_arguments
    _spine_check_arguments.register_command("spine-install-check", _spine_directory_check, False)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renpy-sdk', type=Path, required=True)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    tag = 'v' + (ROOT / 'VERSION').read_text().strip()
    for archived in (False, True):
        with tempfile.TemporaryDirectory(prefix='spine-renpy-') as temp:
            project = Path(temp)
            game = project / 'game'
            game.mkdir()
            with zipfile.ZipFile(args.dist / f'renpy-spine-{tag}-all.zip') as archive:
                archive.extractall(game)
            for version in ('4.0', '4.1', '4.2', '4.3'):
                source = ROOT / 'game/spine/tools/fixtures' / version / 'spineboy/export'
                target = game / 'spine/assets/check' / version
                target.mkdir(parents=True)
                for name in ('spineboy-pro.skel', 'spineboy.atlas', 'spineboy.png'):
                    shutil.copyfile(source / name, target / name)
            (game / 'script.rpy').write_text('define config.name = "Spine install check"\nlabel start:\n    return\n')
            (game / 'python-packages').mkdir()
            (game / 'python-packages/existing_dependency.py').write_text('marker = 117\n')
            (game / 'install_check.rpy').write_text(CHECK, encoding='utf-8')
            if archived:
                archive_modules(game)
                assert not (game / 'spine/python/renpy_spine/__init__.py').exists()
            result = subprocess.run([sys.executable, str(args.renpy_sdk / 'renpy.py'),
                                     str(project), 'spine-install-check'],
                                    env={**os.environ, 'RENPY_DISABLE_JOYSTICK': '1'},
                                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
            output = result.stdout + result.stderr
            if result.returncode or output.count('SPINE INSTALL PASS') != 5:
                print(output)
                raise RuntimeError('Ren\'Py integration check failed')
            print(('RPA' if archived else 'Loose files') + ': ' + output.strip())
            legacy = game / ('python-packages/renpy_spine/__init__.py' if archived else 'spine_runtime.rpy')
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text('# previous plugin installation\n')
            rejected = subprocess.run([sys.executable, str(args.renpy_sdk / 'renpy.py'),
                                       str(project), 'spine-install-check'],
                                      capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
            if not rejected.returncode or 'Old renpy-spine files found' not in rejected.stdout + rejected.stderr:
                raise RuntimeError('Old installation must fail with the migration instructions')
            print('PASS upgrade guard:', legacy.relative_to(game).as_posix())


if __name__ == '__main__':
    main()
