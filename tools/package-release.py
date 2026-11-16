"""Create deterministic source/Windows/Android ZIPs from explicit file lists."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ('3.8', '4.0', '4.1', '4.2', '4.3')
ABIS = ('arm64-v8a', 'armeabi-v7a', 'x86_64')


def files_under(folder, extensions):
    for path in sorted((ROOT / folder).rglob('*')):
        relative = path.relative_to(ROOT)
        if any(part.startswith('.') or part.startswith('vendor') or part in ('fixtures', 'toolchains', '__pycache__')
               for part in path.relative_to(ROOT / folder).parts):
            continue
        if path.is_file() and path.suffix in extensions:
            yield relative.as_posix()


def archive(output, paths):
    paths = sorted(set(paths))
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for relative in paths:
            path = ROOT / relative
            if not path.is_file() or path.is_symlink():
                raise ValueError('Missing or unsafe release input: ' + relative)
            info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zipped.writestr(info, path.read_bytes(), compresslevel=9)
    with zipfile.ZipFile(output) as zipped:
        assert zipped.testzip() is None
        assert sorted(zipped.namelist()) == paths
        assert not any('/vendor' in p or '/fixtures/' in p or 'CH0095' in p or '.spine-check' in p for p in paths)
    return {'name': output.name, 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'files': paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--check-version', action='store_true')
    args = parser.parse_args()
    version = (ROOT / 'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('VERSION must contain a semantic release version')
    tag = 'v' + version
    ref = os.environ.get('GITHUB_REF', '')
    if ref.startswith('refs/tags/') and ref != 'refs/tags/' + tag:
        raise ValueError('Pushed tag must match VERSION: ' + tag)
    if args.check_version:
        print('Validated', tag)
        return
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    common = ['README.md', 'VERSION', 'CHANGELOG.md', 'LICENSE', 'NOTICE']
    common += list(files_under('LICENSES', {'.txt'}))
    common += list(files_under('docs', {'.md'}))
    common += list(files_under('game/python-packages/renpy_spine', {'.py'}))
    common += ['game/spine_runtime.rpy']
    common += [path.relative_to(ROOT).as_posix() for path in sorted((ROOT / 'game/spine').glob('*LICENSE.txt'))]
    common += list(files_under('examples/game', {'.rpy', '.json', '.atlas', '.png'}))
    source = common + list(files_under('game/tools/spine', {'.c', '.cpp', '.ps1', '.cjs', '.py', '.json'}))
    source += list(files_under('tools', {'.py', '.cjs'})) + list(files_under('tests', {'.py'}))
    source += ['.gitignore', '.gitattributes', '.github/workflows/ci.yml']
    windows = common + ['game/tools/spine/package-android.py']
    for spine in VERSIONS:
        name = 'renpy_spine_v1c.dll' if spine == '3.8' else 'renpy_spine_%s.dll' % spine.replace('.', '_')
        windows.append('game/spine/native/windows-x86_64/' + name)
    android = common + ['game/tools/spine/package-android.py']
    for abi in ABIS:
        for spine in VERSIONS:
            name = 'librenpy_spine.so' if spine == '3.8' else 'librenpy_spine_%s.so' % spine.replace('.', '_')
            android.append('game/spine/native/android/' + abi + '/' + name)
    artifacts = []
    for kind, paths in [('source', source), ('windows-x86_64', windows), ('android', android)]:
        result = archive(output / ('renpy-spine-%s-%s.zip' % (tag, kind)), paths)
        if kind == 'source':
            assert not any(p.endswith(('.dll', '.so')) for p in result['files'])
        else:
            count = sum(p.endswith(('.dll', '.so')) for p in result['files'])
            assert count == (5 if kind == 'windows-x86_64' else 15)
        artifacts.append(result)
    manifest = {'version': version, 'tag': tag, 'spine_versions': list(VERSIONS),
                'android_abis': list(ABIS), 'artifacts': artifacts}
    manifest_path = output / 'release-manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    sums = [(item['name'], item['sha256']) for item in artifacts]
    sums.append((manifest_path.name, hashlib.sha256(manifest_path.read_bytes()).hexdigest()))
    (output / 'SHA256SUMS.txt').write_text(''.join(digest + '  ' + name + '\n' for name, digest in sums), encoding='utf-8')
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    marker = '## ' + version + '\n'
    if marker not in changelog:
        raise ValueError('CHANGELOG.md needs a section for ' + version)
    notes = changelog.split(marker, 1)[1].split('\n## ', 1)[0].strip()
    notes += '\n\n附件包含源码、Windows x64 安装包、Android 三种 ABI 安装包、文件清单和 SHA-256。'
    notes += '\n\nSpine 授权条件适用，参见随包 LICENSE、NOTICE 和 docs/LICENSING.md。'
    (output / 'RELEASE_NOTES.md').write_text(notes + '\n', encoding='utf-8')
    print(json.dumps({'tag': tag, 'archives': [{k: a[k] for k in ('name', 'bytes', 'sha256')} for a in artifacts]}, indent=2))


if __name__ == '__main__':
    main()
