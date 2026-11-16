"""Install platform ZIPs into an existing project and preserve its files."""
import argparse
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    tag = 'v' + (ROOT / 'VERSION').read_text().strip()
    contents = {}
    originals = {
        'script.rpy': b'label start:\n    return\n',
        'screens.rpy': b'# existing project screens\n',
        'options.rpy': b'# existing project configuration\n',
        'gui.rpy': b'# existing project UI\n',
        'python-packages/existing_dependency.py': b'marker = 117\n',
        'spine/assets/my_character/model.json': b'{"existing": true}',
        'tools/existing_tool.py': b'# existing project tool\n',
    }
    for kind in ('windows-x86_64', 'android', 'all'):
        with tempfile.TemporaryDirectory(prefix='spine-install-') as temp:
            game = Path(temp) / 'game'
            for name, data in originals.items():
                target = game / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            with zipfile.ZipFile(args.dist / f'renpy-spine-{tag}-{kind}.zip') as archive:
                names = archive.namelist()
                assert all(name.startswith('spine/') and '..' not in Path(name).parts for name in names)
                contents[kind] = {name: archive.read(name) for name in names}
                archive.extractall(game)
            for name, data in originals.items():
                assert (game / name).read_bytes() == data, name
            assert (game / 'spine/spine_runtime.rpy').is_file()
            assert (game / 'spine/python/renpy_spine/displayable.py').is_file()
            assert (game / 'spine/example.rpy').is_file()
            assert (game / 'spine/docs/INSTALLING.md').is_file()
            assert (game / 'spine/LICENSE').is_file() and (game / 'spine/NOTICE').is_file()
            assert not (game / 'spine_runtime.rpy').exists()
            assert not (game / 'python-packages/renpy_spine').exists()
            assert not (game / 'tools/spine').exists()
            print(f'PASS {kind}: one spine directory, existing project files and model preserved')
    for name in contents['windows-x86_64'].keys() & contents['android'].keys():
        assert contents['windows-x86_64'][name] == contents['android'][name], name
    assert contents['all'] == {**contents['windows-x86_64'], **contents['android']}
    print('PASS all package equals the Windows + Android file union')


if __name__ == '__main__':
    main()
