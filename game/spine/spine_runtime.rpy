# Copyright (c) 2026 renpy-spine contributors. See LICENSE and NOTICE.
init -100 python:
    if any(renpy.loadable(_old_spine_path) for _old_spine_path in (
            "spine_runtime.rpy", "spine_runtime.rpyc",
            "python-packages/renpy_spine/__init__.py")):
        raise RuntimeError("Old renpy-spine files found. See spine/docs/INSTALLING.md: "
                           "remove the old game/spine_runtime.rpy and .rpyc and "
                           "game/python-packages/renpy_spine; keep game/spine/assets.")
    # Use Ren'Py's importer so the package also loads from RPA and APK assets.
    renpy.add_python_directory("spine/python")
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
    build.classify("game/spine/python/**", "archive")
    build.classify("game/spine/assets/**", "archive")
    build.classify("game/spine/tools/**", None)
