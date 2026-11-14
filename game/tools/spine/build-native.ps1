param(
    [ValidateSet('windows','android')][string]$Target = 'windows',
    [string]$Ndk = $env:ANDROID_NDK_HOME,
    [string]$OutputRoot
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
# Verify the committed lock before using downloaded source files.
$sourceLock = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'runtime-lock.json') | ConvertFrom-Json
foreach ($entry in $sourceLock.files.PSObject.Properties) {
    $sourcePath = Join-Path $PSScriptRoot ('vendor\' + $entry.Name)
    if (-not (Test-Path -LiteralPath $sourcePath)) { throw 'Run node tools/spine/fetch-runtime.cjs from game before building.' }
    if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw ('Runtime source checksum mismatch: ' + $entry.Name)
    }
}
$include = Join-Path $PSScriptRoot 'vendor\include'
$sources = @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'vendor\src\spine') -Filter '*.c' | ForEach-Object { $_.FullName })
# The pinned C AnimationState assigns attachments without clearing old mesh
# deformation. Match the official JS 3.8 Slot.setAttachment behavior at both
# assignment sites. Generate the corrected file; preserve vendor checksums.
$animationStatePath = Join-Path $PSScriptRoot 'vendor\src\spine\AnimationState.c'
$animationState = [IO.File]::ReadAllText($animationStatePath)
$oldAssignment = 'slot->attachment = attachmentName == NULL ? NULL : spSkeleton_getAttachmentForSlotIndex(skeleton, slot->data->index, attachmentName);'
$newAssignment = 'spSlot_setAttachment(slot, attachmentName == NULL ? NULL : spSkeleton_getAttachmentForSlotIndex(skeleton, slot->data->index, attachmentName));'
if ([regex]::Matches($animationState, [regex]::Escape($oldAssignment)).Count -ne 2) {
    throw 'Spine AnimationState source changed; review the attachment/deform fix before building.'
}
$generated = Join-Path $taskRoot '.spine-check\native-sources\AnimationState.c'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $generated) | Out-Null
[IO.File]::WriteAllText($generated, $animationState.Replace($oldAssignment, $newAssignment))
$sources = @($sources | Where-Object { $_ -ne $animationStatePath })
$sources += $generated
$sources += Join-Path $PSScriptRoot 'bridge.c'
if (-not $OutputRoot) { $OutputRoot = Join-Path $taskRoot 'spine\native' }
$common = @('-std=c99','-O2','-fvisibility=hidden','-I',$include,'-shared')
if ($Target -eq 'windows') {
    $dest = Join-Path $OutputRoot 'windows-x86_64\renpy_spine_v1c.dll'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
    & gcc @common @sources '-static-libgcc' '-Wl,--no-undefined' '-Wl,--dynamicbase' '-Wl,--nxcompat' '-o' $dest '-lm'
    if ($LASTEXITCODE -ne 0) { throw 'Windows compilation failed.' }
    Write-Output $dest
} else {
    if (-not $Ndk) { throw 'Pass -Ndk <Android NDK directory>, or set ANDROID_NDK_HOME. Use NDK r28 or newer for Android 16 KB pages.' }
    $compiler = Join-Path $Ndk 'toolchains\llvm\prebuilt\windows-x86_64\bin\clang.exe'
    if (-not (Test-Path -LiteralPath $compiler)) { throw "NDK clang missing: $compiler" }
    $targets = @{
        'arm64-v8a' = 'aarch64-linux-android21'
        'armeabi-v7a' = 'armv7a-linux-androideabi21'
        'x86_64' = 'x86_64-linux-android21'
    }
    foreach ($abi in $targets.Keys) {
        $dest = Join-Path $OutputRoot "android\$abi\librenpy_spine.so"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        & $compiler "--target=$($targets[$abi])" @common '-fPIC' @sources '-Wl,--no-undefined' '-Wl,-z,max-page-size=16384' '-Wl,-z,common-page-size=16384' '-Wl,-soname,librenpy_spine.so' '-o' $dest '-lm'
        if ($LASTEXITCODE -ne 0) { throw "Android compilation failed: $abi" }
        Write-Output $dest
    }
}
