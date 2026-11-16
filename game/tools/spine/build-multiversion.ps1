param(
    [ValidateSet('windows','android')][string]$Target = 'windows',
    [string]$Ndk = (Join-Path $PSScriptRoot 'toolchains/android-ndk-r28c'),
    [string[]]$Versions = @('4.0','4.1','4.2','4.3'),
    [string]$OutputRoot
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
if (-not $OutputRoot) { $OutputRoot = Join-Path $taskRoot 'spine/native' }
foreach ($version in $Versions) {
    if ($version -notin @('4.0','4.1','4.2','4.3')) { throw "Unsupported backend: $version" }
    $cpp = $version -eq '4.3'
    $vendor = Join-Path $PSScriptRoot "vendor-$version"
    $sourceLock = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot "runtime-lock-$version.json") | ConvertFrom-Json
    foreach ($entry in $sourceLock.files.PSObject.Properties) {
        $sourcePath = Join-Path $vendor $entry.Name
        if (-not (Test-Path -LiteralPath $sourcePath)) { throw 'Run node game/tools/spine/fetch-multiversion.cjs before building.' }
        if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
            throw "Runtime $version checksum mismatch: $($entry.Name)"
        }
    }
    $extension = if ($cpp) { '*.cpp' } else { '*.c' }
    $sources = @(Get-ChildItem -LiteralPath (Join-Path $vendor 'src/spine') -Filter $extension | ForEach-Object { $_.FullName })
    $sources += Join-Path $PSScriptRoot $(if ($cpp) { 'bridge-4.3.cpp' } else { 'bridge-4.c' })
    $tag = $version.Replace('.', '_')
    $common = @('-O2','-fvisibility=hidden','-I',(Join-Path $vendor 'include'),'-shared')
    if ($cpp) { $common += @('-std=c++11','-fvisibility-inlines-hidden') }
    else { $common += @('-std=c99',"-DRSP_MINOR=$($version.Split('.')[1])") }
    if ($Target -eq 'windows') {
        $dest = Join-Path $OutputRoot "windows-x86_64/renpy_spine_$tag.dll"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        $compiler = if ($cpp) { 'g++' } else { 'gcc' }
        $link = @('-static-libgcc','-Wl,--no-undefined','-Wl,--dynamicbase','-Wl,--nxcompat')
        if ($cpp) { $link += @('-static-libstdc++','-static') }
        & $compiler @common @sources @link '-o' $dest '-lm'
        if ($LASTEXITCODE -ne 0) { throw "Compilation failed: $version Windows" }
        Write-Output $dest
    } else {
        $compiler = Join-Path $Ndk 'toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe'
        $targets = @{'arm64-v8a'='aarch64-linux-android21'; 'armeabi-v7a'='armv7a-linux-androideabi21'; 'x86_64'='x86_64-linux-android21'}
        foreach ($abi in $targets.Keys) {
            $name = "librenpy_spine_$tag.so"
            $dest = Join-Path $OutputRoot "android/$abi/$name"
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
            $link = @('-Wl,--no-undefined','-Wl,-z,max-page-size=16384','-Wl,-z,common-page-size=16384',"-Wl,-soname,$name")
            if ($cpp) { $link += @('-lc++_static','-lc++abi','-lunwind') }
            & $compiler "--target=$($targets[$abi])" @common '-fPIC' @sources @link '-o' $dest '-lm'
            if ($LASTEXITCODE -ne 0) { throw "Compilation failed: $version $abi" }
            Write-Output $dest
        }
    }
}
