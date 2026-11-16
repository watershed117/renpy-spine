"""Exercise APK/AAB injection for every shipped ABI and every runtime version."""
import importlib.util
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package_android', ROOT / 'game/tools/spine/package-android.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)

with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    for bundle in (False, True):
        for abis in (('arm64-v8a',), package.ABIS):
            prefix = 'base/' if bundle else ''
            source, dest = folder / 'source.zip', folder / 'injected.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                if bundle:
                    archive.writestr('BundleConfig.pb', b'fixture')
                for abi in abis:
                    archive.writestr(prefix + 'lib/' + abi + '/librenpython.so', b'engine fixture')
                archive.writestr(prefix + 'assets/example', b'assets preserved')
                archive.writestr('META-INF/CERT.SF', b'old signature')
            _, actual = package.inject_package(source, dest)
            assert actual == sorted(abis)
            with zipfile.ZipFile(dest) as archive:
                assert archive.read(prefix + 'assets/example') == b'assets preserved'
                assert 'META-INF/CERT.SF' not in archive.namelist()
                assert len([p for p in archive.namelist() if 'librenpy_spine' in p]) == len(abis) * 5
                if len(abis) == 1:
                    assert not any('/x86_64/' in p or '/armeabi-v7a/' in p for p in archive.namelist())
print('PASS: four APK/AAB layouts, all five backends, original assets and ABI selection')
