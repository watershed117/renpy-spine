# Copyright (c) 2026 renpy-spine contributors. See LICENSE and NOTICE.
init -100 python:
    from renpy_spine.displayable import Spine, register as _register_spine_shader
    from renpy_spine.interaction import SpineInteraction, TouchRegion, PointerBinding
    _register_spine_shader()

init -90 python:
    # ctypes libraries must remain outside RPA archives.
    build.classify("game/spine/native/windows-x86_64/renpy_spine.dll", None)
    build.classify("game/spine/native/windows-x86_64/renpy_spine_v1.dll", None)
    build.classify("game/spine/native/windows-x86_64/renpy_spine_v1b.dll", None)
    build.classify("game/spine/native/windows-x86_64/**", "windows")
    # Inject Android libraries into APK/AAB lib directories after RAPT builds.
    build.classify("game/spine/native/android/**", None)
    build.classify("game/spine/assets/**", "archive")
    build.classify("game/tools/spine/**", None)
