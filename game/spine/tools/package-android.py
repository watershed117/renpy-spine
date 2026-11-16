"""Add Spine to a Ren'Py APK/AAB without modifying Ren'Py or RAPT sources.

Copies the input, adds the library for each ABI already present in the package,
aligns APK native libraries to 16 KB, signs the new output, and verifies it.
Passwords are passed to signing tools through environment variables.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
LIBRARIES = ROOT / 'spine' / 'native' / 'android'
ABIS = ('arm64-v8a', 'armeabi-v7a', 'x86_64')
NAMES = ('librenpy_spine.so',) + tuple('librenpy_spine_4_%d.so' % i for i in range(4))


def inspect_package(filename):
    with zipfile.ZipFile(filename) as package:
        names = package.namelist()
        prefix = 'base/' if 'BundleConfig.pb' in names else ''
        abis = sorted({name.split('/')[1 if not prefix else 2]
                       for name in names if name.startswith(prefix+'lib/') and name.endswith('.so')})
        if not abis:
            raise ValueError('Input has no Android native ABI directories')
        unsupported = set(abis)-set(ABIS)
        if unsupported:
            raise ValueError('Compile the Spine bridge for these additional ABIs: '+', '.join(sorted(unsupported)))
        return prefix, abis


def inject_package(source, destination, libraries=LIBRARIES):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Output must differ from the original package')
    prefix, abis = inspect_package(source)
    for abi in abis:
        for name in NAMES:
            if not (libraries / abi / name).is_file():
                raise FileNotFoundError('Build the native Spine library for '+abi+': '+name)
    paths = {prefix+'lib/'+abi+'/'+name: libraries/abi/name for abi in abis for name in NAMES}
    signature = re.compile(r'^META-INF/(?:[^/]+\.(?:SF|RSA|DSA|EC)|MANIFEST\.MF)$', re.IGNORECASE)
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, 'w', allowZip64=True) as output:
        for info in original.infolist():
            if signature.match(info.filename) or info.filename in paths:
                continue
            # Stream large Ren'Py asset packs instead of loading them into RAM.
            with original.open(info) as reader, output.open(info, 'w') as writer:
                shutil.copyfileobj(reader, writer, length=1024*1024)
        for name, filename in paths.items():
            output.write(filename, name, compress_type=zipfile.ZIP_STORED)
    verify_package(destination, libraries)
    return prefix, abis


def verify_package(filename, libraries=LIBRARIES):
    prefix, abis = inspect_package(filename)
    with zipfile.ZipFile(filename) as package:
        for abi in abis:
            for library_name in NAMES:
                name=prefix+'lib/'+abi+'/'+library_name
                if package.read(name) != (libraries/abi/library_name).read_bytes():
                    raise ValueError('Runtime bytes differ for '+abi+': '+library_name)
                if package.getinfo(name).compress_type != zipfile.ZIP_STORED:
                    raise ValueError('Runtime must be stored uncompressed: '+abi+': '+library_name)
    return abis


def find_sdk(args):
    candidates=[args.sdk,os.environ.get('ANDROID_SDK_ROOT'),os.environ.get('ANDROID_HOME')]
    if args.renpy_sdk:
        rapt=Path(args.renpy_sdk)/'rapt'
        if (rapt/'sdk.txt').is_file():
            candidates.append((rapt/'sdk.txt').read_text().strip())
        candidates.append(rapt/'Sdk')
    for candidate in candidates:
        if candidate and (Path(candidate)/'build-tools').is_dir():
            return Path(candidate)
    raise FileNotFoundError('Pass --sdk <Android SDK>, or --renpy-sdk <Ren\'Py SDK with RAPT installed>')


def build_tools(sdk):
    versions=[p for p in (sdk/'build-tools').iterdir() if p.is_dir()]
    versions.sort(key=lambda p:tuple(int(n) for n in re.findall(r'\d+',p.name)),reverse=True)
    for folder in versions:
        align=folder/('zipalign.exe' if os.name=='nt' else 'zipalign')
        signer=folder/'lib/apksigner.jar'
        if align.is_file() and signer.is_file():
            return align,signer
    raise FileNotFoundError('Android build-tools with zipalign and apksigner are required')


def java_tool(name):
    if os.environ.get('JAVA_HOME'):
        candidate=Path(os.environ['JAVA_HOME'])/'bin'/(name+('.exe' if os.name=='nt' else ''))
        if candidate.is_file():
            return str(candidate)
    candidate=shutil.which(name)
    if not candidate:
        raise FileNotFoundError('JDK tool not found: '+name)
    return candidate


def run(command, env=None):
    subprocess.run([str(x) for x in command],check=True,env=env)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path,help='Ren\'Py APK or AAB; the original is preserved')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--sdk',type=Path)
    parser.add_argument('--renpy-sdk',type=Path)
    parser.add_argument('--keystore',type=Path)
    parser.add_argument('--alias',default='android',help='RAPT default: android')
    parser.add_argument('--store-pass-env',default='SPINE_STORE_PASSWORD')
    parser.add_argument('--key-pass-env',default='SPINE_KEY_PASSWORD')
    parser.add_argument('--unsigned',action='store_true',help='Produce unsigned output for an external signing pipeline')
    args=parser.parse_args()
    source=args.package.resolve()
    if source.suffix.lower() not in ('.apk','.aab'):
        parser.error('Input must be an APK or AAB')
    output=(args.output or source.with_name(source.stem+'-spine'+source.suffix)).resolve()
    if output==source or output.exists():
        parser.error('Choose a new output filename; existing files are never overwritten')
    prefix,abis=inspect_package(source)
    if bool(prefix) != (source.suffix.lower()=='.aab'):
        parser.error('Package structure does not match its extension')
    output.parent.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    env.setdefault(args.store_pass_env,'android')  # RAPT's existing default keys
    env.setdefault(args.key_pass_env,env[args.store_pass_env])
    keystore=(args.keystore or ROOT.parent/('bundle.keystore' if prefix else 'android.keystore')).resolve()
    align,signer=(None,None) if prefix else build_tools(find_sdk(args))
    if not args.unsigned and not keystore.is_file():
        parser.error('Signing keystore not found. Build/configure RAPT first, pass --keystore, or explicitly use --unsigned')
    with tempfile.TemporaryDirectory(prefix='spine-package-',dir=output.parent) as temp:
        temp=Path(temp)
        injected=temp/('injected.aab' if prefix else 'injected.apk')
        inject_package(source,injected)
        if prefix:
            if not args.unsigned:
                run([java_tool('jarsigner'),'-keystore',keystore,'-storepass:env',args.store_pass_env,
                     '-keypass:env',args.key_pass_env,injected,args.alias],env)
                run([java_tool('jarsigner'),'-verify',injected],env)
            verify_package(injected)
            shutil.copyfile(injected,output)
        else:
            aligned=temp/'aligned.apk'
            run([align,'-P','16','-f','4',injected,aligned])
            if args.unsigned:
                shutil.copyfile(aligned,output)
            else:
                signed=temp/'signed.apk'
                run([java_tool('java'),'-jar',signer,'sign','--ks',keystore,'--ks-key-alias',args.alias,
                     '--ks-pass','env:'+args.store_pass_env,'--key-pass','env:'+args.key_pass_env,
                     '--out',signed,aligned],env)
                run([java_tool('java'),'-jar',signer,'verify','--verbose',signed],env)
                run([align,'-c','-P','16','4',signed])
                verify_package(signed)
                shutil.copyfile(signed,output)
    print('Spine native ABIs: '+', '.join(abis))
    print(('UNSIGNED: ' if args.unsigned else 'Signed: ')+str(output))


if __name__=='__main__':
    main()
