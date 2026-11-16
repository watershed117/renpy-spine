"""Check all five backends, source locks, target machines and native dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ('3.8', '4.0', '4.1', '4.2', '4.3')


def elf_info(filename):
    data = filename.read_bytes()
    assert data[:4] == b'\x7fELF' and data[5] == 1, filename
    wide = data[4] == 2
    machine = struct.unpack_from('<H', data, 18)[0]
    phoff = struct.unpack_from('<Q' if wide else '<I', data, 32 if wide else 28)[0]
    stride, count = struct.unpack_from('<HH', data, 54 if wide else 42)
    segments = []
    for i in range(count):
        values = struct.unpack_from('<IIQQQQQQ' if wide else '<IIIIIIII', data, phoff + i * stride)
        if wide:
            kind, flags, offset, address, physical, size, memory, align = values
        else:
            kind, offset, address, physical, size, memory, flags, align = values
        segments.append((kind, offset, address, size, align))
    load = [s for s in segments if s[0] == 1]
    dynamic = next(s for s in segments if s[0] == 2)
    tags = []
    for p in range(dynamic[1], dynamic[1] + dynamic[3], 16 if wide else 8):
        tag, value = struct.unpack_from('<QQ' if wide else '<II', data, p)
        if not tag:
            break
        tags.append((tag, value))
    straddr = next(v for k, v in tags if k == 5)
    segment = next(s for s in load if s[2] <= straddr < s[2] + s[3])
    stroff = segment[1] + straddr - segment[2]
    needed = []
    for tag, value in tags:
        if tag == 1:
            start = stroff + value
            needed.append(data[start:data.index(0, start)].decode())
    assert all(s[4] >= 16384 and s[1] % 16384 == s[2] % 16384 for s in load), filename
    assert set(needed) <= {'libc.so', 'libm.so', 'libdl.so'}, (filename, needed)
    return {'machine': machine, 'page_alignment': min(s[4] for s in load), 'dependencies': needed}


def pe_info(filename):
    data = filename.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    assert data[:2] == b'MZ' and data[pe:pe + 4] == b'PE\0\0'
    machine, count = struct.unpack_from('<HH', data, pe + 4)
    assert machine == 0x8664
    optsize, = struct.unpack_from('<H', data, pe + 20)
    opt = pe + 24
    assert struct.unpack_from('<H', data, opt)[0] == 0x20b
    sections = []
    for i in range(count):
        p = opt + optsize + i * 40
        virtualsize, address, rawsize, raw = struct.unpack_from('<IIII', data, p + 8)
        sections.append((address, max(virtualsize, rawsize), raw))
    def offset(rva):
        address, size, raw = next(s for s in sections if s[0] <= rva < s[0] + s[1])
        return raw + rva - address
    imports, = struct.unpack_from('<I', data, opt + 120)
    p = offset(imports)
    needed = []
    while any(data[p:p + 20]):
        name, = struct.unpack_from('<I', data, p + 12)
        start = offset(name)
        needed.append(data[start:data.index(0, start)].decode())
        p += 20
    system = {'kernel32.dll', 'msvcrt.dll', 'ucrtbase.dll', 'user32.dll', 'advapi32.dll', 'ntdll.dll', 'bcrypt.dll'}
    assert all(name.lower() in system or name.lower().startswith('api-ms-win-') for name in needed), (filename, needed)
    return {'machine': 'x86_64', 'dependencies': needed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=('windows', 'android', 'all'), default='all')
    args = parser.parse_args()
    report = {'sources': {}, 'libraries': {}}
    for version in VERSIONS:
        suffix = '' if version == '3.8' else '-' + version
        lock = json.loads((ROOT / ('game/tools/spine/runtime-lock%s.json' % suffix)).read_text())
        vendor = ROOT / ('game/tools/spine/vendor' + suffix)
        for relative, expected in lock['files'].items():
            assert hashlib.sha256((vendor / relative).read_bytes()).hexdigest() == expected, (version, relative)
        report['sources'][version] = {'revision': lock['revision'], 'unchanged_files': len(lock['files'])}
    if args.target in ('windows', 'all'):
        for version in VERSIONS:
            name = 'renpy_spine_v1c.dll' if version == '3.8' else 'renpy_spine_%s.dll' % version.replace('.', '_')
            filename = ROOT / 'game/spine/native/windows-x86_64' / name
            info = pe_info(filename)
            info['sha256'] = hashlib.sha256(filename.read_bytes()).hexdigest()
            report['libraries']['windows-x86_64/' + name] = info
    if args.target in ('android', 'all'):
        for abi, machine in [('arm64-v8a', 183), ('armeabi-v7a', 40), ('x86_64', 62)]:
            for version in VERSIONS:
                name = 'librenpy_spine.so' if version == '3.8' else 'librenpy_spine_%s.so' % version.replace('.', '_')
                filename = ROOT / 'game/spine/native/android' / abi / name
                info = elf_info(filename)
                assert info['machine'] == machine, filename
                info['sha256'] = hashlib.sha256(filename.read_bytes()).hexdigest()
                report['libraries'][abi + '/' + name] = info
    output = ROOT / ('reports/native-audit-%s.json' % args.target)
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS:', len(report['libraries']), 'libraries;', sum(s['unchanged_files'] for s in report['sources'].values()), 'official files')


if __name__ == '__main__':
    main()
