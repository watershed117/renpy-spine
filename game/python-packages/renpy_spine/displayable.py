"""Real-time Spine displayable using Ren'Py's existing model renderer.

GPU mesh objects and ctypes handles live in a transient weak cache. Save files
contain only strings, numbers, and versioned snapshots without native pointers.
"""
import ctypes as C
import math
import os
import weakref

import renpy
import renpy.exports as exports
from renpy.display.displayable import Displayable
from renpy.display.render import Render
from renpy_spine.native import Native, load_library, skeleton_version, runtime_version

_library = None
_libraries = {}
_layout = None
_sessions = weakref.WeakKeyDictionary()


def register():
    exports.register_shader(
        "renpy_spine.tint",
        variables="""
            attribute vec4 a_rsp_light;
            attribute vec3 a_rsp_dark;
            varying vec4 v_rsp_light;
            varying vec3 v_rsp_dark;
        """,
        vertex_300="""
            v_rsp_light = a_rsp_light;
            v_rsp_dark = a_rsp_dark;
        """,
        fragment_300="""
            vec4 rsp_tex = gl_FragColor;
            gl_FragColor = vec4(
                rsp_tex.rgb * v_rsp_light.rgb +
                (rsp_tex.a - rsp_tex.rgb) * v_rsp_dark,
                rsp_tex.a * v_rsp_light.a);
        """,
    )


def library(version='3.8'):
    global _library
    if version not in ('3.8', '4.0', '4.1', '4.2', '4.3'):
        raise ValueError('Unsupported Spine runtime: ' + version)
    if version not in _libraries:
        android_name = 'librenpy_spine.so' if version == '3.8' else 'librenpy_spine_%s.so' % version.replace('.', '_')
        windows_name = 'renpy_spine_v1c.dll' if version == '3.8' else 'renpy_spine_%s.dll' % version.replace('.', '_')
        if renpy.android:
            try:
                loaded = load_library(android_name)
            except OSError:
                # RAPT uses extracted native libraries. Never dlopen an asset
                # copied into writable game/cache directories on Android.
                from jnius import autoclass
                activity = autoclass("org.renpy.android.PythonSDLActivity").mActivity
                folder = str(activity.getApplicationInfo().nativeLibraryDir)
                try:
                    loaded = load_library(os.path.join(folder, android_name))
                except OSError as error:
                    raise RuntimeError("Spine native library is missing from this APK. "
                                       "Run tools/spine/package-android.py after the Ren'Py Android build.") from error
        elif renpy.windows:
            loaded = load_library(os.path.join(renpy.config.gamedir, "spine", "native",
                                               "windows-x86_64", windows_name))
        else:
            raise RuntimeError("This project includes native Spine builds for Windows x64 and Android. "
                               "Other platforms require compiling the matching bridge for that platform.")
        if loaded.spine_version != version:
            raise RuntimeError('Spine native library version mismatch: ' + version)
        _libraries[version] = loaded
        if version == '3.8':
            _library = loaded
    return _libraries[version]


def _read(path):
    with exports.open_file(path) as source:
        return source.read()


class _Control(renpy.python.RevertableObject):
    def __init__(self):
        self.revision = 0
        self.snapshot = None
        self.anchor = None
        self.overrides = ()
        self.skin = None
        self.mixes = ()
        self.paused = False
        self.speed = 1.0


class _MeshBuffers:
    """Submit changed mesh streams, retaining owned byte snapshots for comparison."""
    def __init__(self, layout, batch):
        from renpy.gl2.gl2mesh2 import Mesh2
        self.counts = (batch.vertices, batch.indices // 3)
        self.mesh = Mesh2(layout, *self.counts)
        self.geometry = self.attributes = self.triangles = None

    def upload(self, batch):
        # Mesh2 consumes Python sequences element by element. ctypes slices
        # produce lists in C, avoiding per-element array/memoryview lookups in
        # its setters. UV/tint and topology often stay identical across frames;
        # compare complete bytes, since equal counts do not imply equal data.
        geometry = C.string_at(batch.xy, batch.vertices * 8)
        if geometry != self.geometry:
            self.mesh.set_geometry_data(
                (C.c_float * (batch.vertices * 2)).from_address(C.addressof(batch.xy.contents))[:])
            self.geometry = geometry
        attributes = C.string_at(batch.attributes, batch.vertices * 36)
        if attributes != self.attributes:
            self.mesh.set_attribute_data(
                (C.c_float * (batch.vertices * 9)).from_address(C.addressof(batch.attributes.contents))[:])
            self.attributes = attributes
        triangles = C.string_at(batch.triangles, batch.indices * 4)
        if triangles != self.triangles:
            self.mesh.set_triangle_data(
                (C.c_uint32 * batch.indices).from_address(C.addressof(batch.triangles.contents))[:])
            self.triangles = triangles


class _Session:
    def __init__(self, owner):
        data = _read(owner.skeleton)
        is_json = owner.skeleton.lower().endswith('.json')
        version = runtime_version(skeleton_version(data, is_json))
        self.native = Native(library(version), _read(owner.atlas), data,
                             owner.skeleton_scale, is_json)
        folder = owner.atlas.rsplit("/", 1)[0]
        self.textures = [renpy.display.im.unoptimized_texture(renpy.easy.displayable(folder + "/" + page))
                         for page in self.native.pages]
        self.meshes = []
        self.last_st = None
        self.skip_next_delta = False
        self.revision = -1
        self.applied_overrides = set()
        self.pointer_overrides = {}
        self.stats = {}
        self.native.default_mix(owner.default_mix)

    def sync(self, owner, st=None):
        control = owner.control
        if self.revision != control.revision:
            self.native.default_mix(owner.default_mix)
            if control.skin:
                self.native.skin(control.skin)
            for a, b, duration in control.mixes:
                self.native.mix(a, b, duration)
            if control.snapshot is not None:
                self.native.restore(control.snapshot)
            else:
                self.native.clear()
                if owner.animation:
                    self.native.play(owner.animation, loop=owner.loop)
            resume = getattr(owner, "_resume", None)
            if resume and resume[0] == control.revision:
                self.native.restore(resume[1])
                owner._resume = None
            self.native.events()  # restoring a save does not repeat old events
            overrides = dict(control.overrides)
            for name in (self.applied_overrides | set(self.native.overrides)) - set(overrides) - set(self.pointer_overrides):
                self.native.override(name)
            for name, values in overrides.items():
                fields = dict(values)
                fields.update(self.pointer_overrides.get(name, {}))
                self.native.override(name, **fields)
            for name, values in self.pointer_overrides.items():
                if name not in overrides:
                    self.native.override(name, **values)
            self.applied_overrides = set(overrides)
            self.last_st = control.anchor if control.anchor is not None else owner._started_st
            if resume and resume[0] == control.revision:
                self.last_st = resume[2]
            self.revision = control.revision
        if st is not None:
            if owner._started_st is None:
                owner._started_st = st
            if self.last_st is None or st < self.last_st:
                self.last_st = min(st, owner._started_st) if self.last_st is None else st
            if self.skip_next_delta:
                self.last_st = st
                self.skip_next_delta = False
            delta = max(0.0, st - self.last_st)
            if control.paused:
                delta = 0.0
            # Advance in bounded steps for mixing/event ordering after a stall.
            remaining = delta * control.speed
            while remaining > 1e-7:
                step = min(remaining, 1.0 / 30.0)
                self.native.update(step)
                remaining -= step
            if delta == 0.0:
                self.native.update(0.0)
            self.last_st = st


class Spine(Displayable):
    """A Spine 3.8 or 4.0-4.3 skeleton, animated live by its official runtime.

    ``size`` is a fixed Ren'Py canvas. ``origin`` is the canvas coordinate of
    Spine (0, 0). ``zoom`` is independent of the skeleton export scale.
    Bone x/y stay in Spine coordinates (y up).
    """
    def __init__(self, skeleton, atlas=None, animation=None, loop=True,
                 size=(1920, 1080), origin=(960, 900), zoom=1.0,
                 skeleton_scale=1.0, default_mix=0.2, fps=60, **properties):
        super().__init__(**properties)
        self.skeleton = skeleton.replace("\\", "/")
        self.atlas = (atlas or os.path.splitext(self.skeleton)[0] + ".atlas").replace("\\", "/")
        self.animation, self.loop = animation, bool(loop)
        self.size, self.origin = tuple(size), tuple(origin)
        self.zoom, self.skeleton_scale = float(zoom), float(skeleton_scale)
        self.default_mix, self.fps = float(default_mix), float(fps)
        if not all(math.isfinite(v) for v in (self.zoom, self.skeleton_scale, self.default_mix, self.fps)) or self.zoom <= 0 or self.skeleton_scale <= 0 or self.default_mix < 0 or self.fps <= 0:
            raise ValueError("Spine zoom, scale, fps must be positive; mix must be nonnegative")
        self.control = _Control()
        self._resume = None
        self._started_st = None

    def _session(self):
        session = _sessions.get(self)
        if session is None:
            session = _Session(self)
            _sessions[self] = session
        session.sync(self)
        return session

    def _changed(self, session):
        self.control.snapshot = session.native.snapshot()
        self.control.anchor = session.last_st
        self.control.revision += 1
        session.revision = self.control.revision
        exports.redraw(self, 0)

    @property
    def animations(self):
        return dict(self._session().native.animations)

    @property
    def bones(self):
        return tuple(self._session().native.bones)

    @property
    def stats(self):
        return dict(self._session().stats)

    def play(self, animation, track=0, loop=True, alpha=1.0, additive=False):
        session = self._session()
        session.native.play(animation, track, loop, alpha, additive)
        self._changed(session)

    def queue(self, animation, track=0, loop=False, delay=0.0, alpha=1.0, additive=False):
        session = self._session()
        session.native.play(animation, track, loop, alpha, additive, True, delay)
        self._changed(session)

    def clear(self, track=-1, mix=0.2):
        session = self._session()
        session.native.clear(track, mix)
        self._changed(session)

    def queue_empty(self, track=1, mix=0.2, delay=0.0):
        session = self._session()
        session.native.empty(track, mix, queued=True, delay=delay)
        self._changed(session)

    def set_skin(self, skin):
        session = self._session()
        session.native.skin(skin)
        self.control.skin = skin
        self._changed(session)

    def set_mix(self, before, after, duration):
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("Mix duration must be nonnegative")
        session = self._session()
        session.native.mix(before, after, duration)
        mixes = {(a,b):d for a,b,d in self.control.mixes}
        mixes[before, after] = duration
        self.control.mixes = tuple((a,b,d) for (a,b),d in mixes.items())
        self._changed(session)

    def set_bone(self, name, **values):
        session = self._session()
        current = dict(self.control.overrides)
        fields = dict(current.get(name, ()))
        fields.update(values)
        session.native.override(name, **fields)
        current[name] = tuple(fields.items())
        self.control.overrides = tuple(current.items())
        session.applied_overrides.add(name)
        session.native.update(0)
        self._changed(session)

    def reset_bone(self, name):
        session = self._session()
        session.native.override(name)
        current = dict(self.control.overrides)
        current.pop(name, None)
        self.control.overrides = tuple(current.items())
        session.native.update(0)
        self._changed(session)

    def get_bone(self, name):
        return self._session().native.bone(name)

    def set_paused(self, paused=True):
        session = self._session()
        self.control.paused = bool(paused)
        session.skip_next_delta = True
        self._changed(session)

    def set_speed(self, speed):
        if not math.isfinite(speed) or speed < 0:
            raise ValueError("Spine speed must be finite and nonnegative")
        session = self._session()
        self.control.speed = float(speed)
        self._changed(session)

    def set_view(self, origin=None, zoom=None):
        """Change framing without restarting animation or rebuilding the rig."""
        point = tuple(origin) if origin is not None else self.origin
        scale = float(zoom) if zoom is not None else self.zoom
        if len(point) != 2 or not all(math.isfinite(v) for v in point) or not math.isfinite(scale) or scale <= 0:
            raise ValueError("Spine origin must be finite and zoom must be positive")
        self.origin, self.zoom = point, scale
        exports.redraw(self, 0)

    def events(self):
        """Poll on an interaction/timer; callbacks are never run from render."""
        return self._session().native.events()

    def canvas_to_bone(self, name, x, y):
        """Convert displayable-local canvas pixels to an animated bone's space."""
        a, b, c, d, tx, ty = self._session().native.bone_matrix(name)
        determinant = a * d - b * c
        if abs(determinant) < 1e-8:
            return None  # A collapsed bone has no meaningful hit region.
        wx = (x - self.origin[0]) / self.zoom - tx
        wy = (self.origin[1] - y) / self.zoom - ty
        return ((d * wx - b * wy) / determinant,
                (a * wy - c * wx) / determinant)

    def bone_to_canvas(self, name, x=0.0, y=0.0):
        a, b, c, d, tx, ty = self._session().native.bone_matrix(name)
        return (self.origin[0] + (a * x + b * y + tx) * self.zoom,
                self.origin[1] - (c * x + d * y + ty) * self.zoom)

    def _pointer_bones(self, values):
        """Transient input overlays; never write pointer samples into rollback."""
        session = self._session()
        persistent = dict(self.control.overrides)
        for name in set(session.pointer_overrides) | set(values):
            fields = dict(persistent.get(name, ()))
            fields.update(values.get(name, {}))
            session.native.override(name, **fields)
        session.pointer_overrides = values
        session.native.update(0.0)
        exports.redraw(self, 0)

    def visit(self):
        # Predict textures even before a native session is created.
        session = _sessions.get(self)
        return list(session.textures) if session else []

    def render(self, width, height, st, at):
        global _layout
        if not renpy.display.render.models:
            raise RuntimeError("Spine requires Ren'Py's GL2/ANGLE2 model renderer")
        if _layout is None:
            from renpy.gl2.gl2mesh import AttributeLayout
            _layout = AttributeLayout()
            _layout.add_attribute("a_tex_coord", 2)
            _layout.add_attribute("a_rsp_light", 4)
            _layout.add_attribute("a_rsp_dark", 3)
        session = self._session()
        session.sync(self, st)
        batches = session.native.draw(self.zoom, self.origin)
        result = Render(*self.size)
        textures = [renpy.display.im.render_for_texture(texture, self.size[0], self.size[1], st, at)
                    for texture in session.textures]
        for index, batch in enumerate(batches):
            counts = (batch.vertices, batch.indices // 3)
            if index >= len(session.meshes):
                session.meshes.append(None)
            cached = session.meshes[index]
            if cached is None or cached.counts != counts:
                cached = _MeshBuffers(_layout, batch)
                session.meshes[index] = cached
            cached.upload(batch)
            model = Render(*self.size)
            model.blit(textures[batch.page], (0, 0), focus=False)
            model.mesh = cached.mesh
            model.add_shader("renpy.texture")
            model.add_shader("renpy_spine.tint")
            blend = ("normal", "add", "multiply", "screen")[batch.blend]
            if blend == "screen":
                blend_function = (32774, 1, 769, 32774, 0, 1)
            else:
                blend_function = renpy.config.gl_blend_func[blend]
            model.add_property("gl_blend_func", blend_function)
            result.blit(model, (0, 0), focus=False)
        session.stats = {"batches": len(batches), "vertices": sum(b.vertices for b in batches),
                         "bones": len(session.native.bones), "bounds": session.native.bounds()}
        if not self.control.paused and self.control.speed:
            exports.redraw(self, 1.0 / self.fps)
        return result

    def __getstate__(self):
        state = super().__getstate__()
        session = _sessions.get(self)
        if session is not None:
            state["_resume"] = (self.control.revision, session.native.snapshot(), session.last_st)
        return state
