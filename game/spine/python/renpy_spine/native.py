"""Python-ABI-independent interface to versioned official Spine backends."""
import ctypes as C
import hashlib
import json
import math
import re
import struct
import zlib

SUPPORTED_VERSIONS = ('3.8', '4.0', '4.1', '4.2', '4.3')


def runtime_version(version):
    match = re.fullmatch(r'(3\.8|4\.[0-3])\.\d+(?:[-\w.]*)?', version)
    if not match or version == '3.8.75':
        raise ValueError('Unsupported Spine export %s; supported versions: %s' %
                         (version, ', '.join(SUPPORTED_VERSIONS)))
    return match.group(1)


class Batch(C.Structure):
    _fields_ = [("page", C.c_int), ("blend", C.c_int),
                ("vertices", C.c_int), ("indices", C.c_int),
                ("xy", C.POINTER(C.c_float)),
                ("attributes", C.POINTER(C.c_float)),
                ("triangles", C.POINTER(C.c_uint32)),
                ("vertex_capacity", C.c_int), ("index_capacity", C.c_int)]


class Event(C.Structure):
    _fields_ = [("type", C.c_int), ("track", C.c_int), ("integer", C.c_int),
                ("time", C.c_float), ("number", C.c_float),
                ("volume", C.c_float), ("balance", C.c_float),
                ("name", C.c_char * 192), ("text", C.c_char * 512),
                ("audio", C.c_char * 384)]


def skeleton_version(data, is_json=False):
    if is_json:
        return json.loads(data.decode("utf-8-sig"))["skeleton"]["spine"]
    offset = 0

    def string():
        nonlocal offset
        length, shift = 0, 0
        while True:
            if offset >= len(data) or shift > 28:
                raise ValueError("Invalid Spine binary header")
            b = data[offset]
            offset += 1
            length |= (b & 127) << shift
            if b < 128:
                break
            shift += 7
        length = max(0, length - 1)
        if offset + length > len(data):
            raise ValueError("Truncated Spine binary header")
        result = data[offset:offset + length].decode("utf-8")
        offset += length
        return result

    # 3.8 stores the hash as a string. 4.x stores an eight-byte integer.
    for modern in (True, False):
        try:
            offset = 8 if modern else 0
            if not modern:
                string()
            version = string()
            if re.fullmatch(r'\d+\.\d+\.\d+(?:[-\w.]*)?', version):
                return version
        except (ValueError, UnicodeError):
            pass
    raise ValueError('Invalid or unrecognized Spine binary version header')


def load_library(path):
    lib = C.CDLL(str(path))
    pointer = C.c_void_p
    string = C.c_char_p
    integer = C.c_int
    floating = C.c_float
    signatures = {
        "rsp_abi": (integer, []),
        "rsp_create": (pointer, [string, integer, string, integer, integer, floating, pointer, integer]),
        "rsp_dispose": (None, [pointer]),
        "rsp_animation_count": (integer, [pointer]),
        "rsp_animation_name": (string, [pointer, integer]),
        "rsp_animation_duration": (floating, [pointer, integer]),
        "rsp_bone_count": (integer, [pointer]),
        "rsp_bone_name": (string, [pointer, integer]),
        "rsp_page_count": (integer, [pointer]),
        "rsp_page_name": (string, [pointer, integer]),
        "rsp_skin": (integer, [pointer, string]),
        "rsp_default_mix": (None, [pointer, floating]),
        "rsp_mix": (integer, [pointer, string, string, floating]),
        "rsp_play": (integer, [pointer, integer, string, integer, floating, integer, integer, floating]),
        "rsp_clear": (None, [pointer, integer, floating]),
        "rsp_empty": (integer, [pointer, integer, floating, integer, floating]),
        "rsp_override": (integer, [pointer, string, integer, C.POINTER(floating)]),
        "rsp_bone": (integer, [pointer, string, C.POINTER(floating)]),
        "rsp_bone_matrix": (integer, [pointer, string, C.POINTER(floating)]),
        "rsp_update": (None, [pointer, floating]),
        "rsp_draw": (integer, [pointer, floating, floating, floating]),
        "rsp_batch": (C.POINTER(Batch), [pointer, integer]),
        "rsp_bounds": (None, [pointer, C.POINTER(floating)]),
        "rsp_events": (integer, [pointer, C.POINTER(Event), integer]),
        "rsp_snapshot": (integer, [pointer, pointer]),
        "rsp_restore": (integer, [pointer, pointer, integer]),
        "rsp_track_size": (integer, []),
    }
    lib.rsp_abi.restype = integer
    lib.rsp_abi.argtypes = []
    abi = lib.rsp_abi()
    for name, (restype, argtypes) in signatures.items():
        if abi == 2 and name in ('rsp_snapshot', 'rsp_restore', 'rsp_track_size'):
            continue
        function = getattr(lib, name)
        function.restype, function.argtypes = restype, argtypes
    if abi not in (1, 2):
        raise RuntimeError("Spine bridge ABI mismatch; rebuild the project runtime")
    lib.spine_version = '3.8'
    if abi == 2:
        lib.rsp_runtime_version.restype = string
        lib.rsp_runtime_version.argtypes = []
        lib.spine_version = lib.rsp_runtime_version().decode('ascii')
    return lib


def _nonnegative(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(name + " must be a finite nonnegative number")
    return value


class Native:
    def __init__(self, lib, atlas, skeleton, scale=1.0, is_json=False):
        self.lib, self.handle = lib, None
        version = skeleton_version(skeleton, is_json)
        self.version = runtime_version(version)
        if self.version != lib.spine_version:
            raise ValueError('Spine %s export requires its matching runtime (loaded %s)' %
                             (version, lib.spine_version))
        modern = self.version != '3.8'
        self._source = (atlas, skeleton, scale, is_json) if modern else None
        self._snapshot_prefix = None
        if modern:
            signature = hashlib.sha256(atlas)
            signature.update(skeleton)
            signature.update(struct.pack('<f', scale))
            self._snapshot_prefix = b'RSPJ1' + self.version.encode('ascii') + signature.digest()
        self._journal = bytearray() if modern else None
        self._replaying = False
        self.overrides = {}
        error = C.create_string_buffer(2048)
        self.handle = lib.rsp_create(atlas, len(atlas), skeleton, len(skeleton),
                                     is_json, float(scale), error, len(error))
        if not self.handle:
            raise ValueError(error.value.decode("utf-8", "replace"))
        self.animations = {
            lib.rsp_animation_name(self.handle, i).decode("utf-8"):
            lib.rsp_animation_duration(self.handle, i)
            for i in range(lib.rsp_animation_count(self.handle))}
        self.pages = [lib.rsp_page_name(self.handle, i).decode("utf-8")
                      for i in range(lib.rsp_page_count(self.handle))]
        self.bones = [lib.rsp_bone_name(self.handle, i).decode("utf-8")
                      for i in range(lib.rsp_bone_count(self.handle))]
        self._event_buffer = (Event * 16)()

    def _record(self, operation, *arguments):
        if self._journal is not None and not self._replaying:
            payload = json.dumps((operation, arguments), ensure_ascii=False,
                                 separators=(',', ':'), allow_nan=False).encode('utf-8')
            self._journal.extend(struct.pack('<I', len(payload)))
            self._journal.extend(payload)

    def default_mix(self, duration):
        duration = _nonnegative(duration, 'mix')
        self.lib.rsp_default_mix(self.handle, duration)
        self._record('default_mix', duration)

    def mix(self, before, after, duration):
        duration = _nonnegative(duration, 'mix')
        if not self.lib.rsp_mix(self.handle, before.encode('utf-8'), after.encode('utf-8'), duration):
            raise ValueError('Unknown Spine animation in mix')
        self._record('mix', before, after, duration)

    def close(self):
        if self.handle:
            self.lib.rsp_dispose(self.handle)
            self.handle = None

    def __del__(self):
        if getattr(self, "handle", None):
            self.close()

    def play(self, name, track=0, loop=True, alpha=1.0, additive=False, queued=False, delay=0.0):
        if name not in self.animations:
            raise ValueError("Unknown Spine animation: " + name)
        if not 0 <= track <= 31:
            raise ValueError("Spine track must be between 0 and 31")
        if not 0 <= alpha <= 1 or not math.isfinite(delay):
            raise ValueError("Invalid animation alpha or queue delay")
        if not self.lib.rsp_play(self.handle, track, name.encode("utf-8"), loop, alpha, additive, queued, delay):
            raise RuntimeError("Could not play Spine animation: " + name)
        self._record('play', name, track, loop, alpha, additive, queued, delay)

    def clear(self, track=-1, mix=0.2):
        if not -1 <= track <= 31:
            raise ValueError("Invalid Spine track")
        self.lib.rsp_clear(self.handle, track, _nonnegative(mix, "mix"))
        self._record('clear', track, mix)

    def skin(self, name):
        if not self.lib.rsp_skin(self.handle, name.encode("utf-8")):
            raise ValueError("Unknown Spine skin: " + name)
        self._record('skin', name)

    def empty(self, track=1, mix=0.2, queued=False, delay=0.0):
        if not 0 <= track <= 31 or not math.isfinite(delay):
            raise ValueError("Invalid empty-animation track or delay")
        self.lib.rsp_empty(self.handle, track, _nonnegative(mix, "mix"), queued, delay)
        self._record('empty', track, mix, queued, delay)

    def override(self, name, **values):
        keys = ("x", "y", "rotation", "scale_x", "scale_y", "shear_x", "shear_y")
        if set(values) - set(keys):
            raise ValueError("Unknown bone field")
        if not all(math.isfinite(v) for v in values.values()):
            raise ValueError("Bone values must be finite")
        mask = sum(1 << i for i, key in enumerate(keys) if key in values)
        data = (C.c_float * 7)(*(values.get(key, 0) for key in keys))
        if not self.lib.rsp_override(self.handle, name.encode("utf-8"), mask, data):
            raise ValueError("Unknown Spine bone: " + name)
        if values:
            self.overrides[name] = dict(values)
        else:
            self.overrides.pop(name, None)
        self._record('override', name, values)

    def bone(self, name):
        data = (C.c_float * 5)()
        if not self.lib.rsp_bone(self.handle, name.encode("utf-8"), data):
            raise ValueError("Unknown Spine bone: " + name)
        return dict(zip(("world_x", "world_y", "x", "y", "rotation"), data))

    def update(self, delta):
        delta = _nonnegative(delta, 'delta')
        self.lib.rsp_update(self.handle, delta)
        if self._journal is not None and not self._replaying:
            # Fixed-size update records keep frame recording cheap. Keep the
            # float32 bits passed to the native runtime, including zero steps.
            self._journal.extend(struct.pack('<If', 0, delta))

    def bone_matrix(self, name):
        data = (C.c_float * 6)()
        if not self.lib.rsp_bone_matrix(self.handle, name.encode("utf-8"), data):
            raise ValueError("Unknown Spine bone: " + name)
        return tuple(data)

    def draw(self, scale=1.0, origin=(0.0, 0.0)):
        count = self.lib.rsp_draw(self.handle, scale, origin[0], origin[1])
        if self._journal is not None and not self._replaying:
            # Drawing applies atlas sequences in official runtimes. Reproduce
            # those operations when restoring, without saving GPU resources.
            self._journal.extend(struct.pack('<I', 1))
        return [self.lib.rsp_batch(self.handle, i).contents for i in range(count)]

    def bounds(self):
        data = (C.c_float * 4)()
        self.lib.rsp_bounds(self.handle, data)
        return tuple(data)

    def events(self):
        data = self._event_buffer
        result = []
        while True:
            count = self.lib.rsp_events(self.handle, data, len(data))
            for i in range(count):
                event = data[i]
                result.append({name: (getattr(event, name).decode("utf-8", "replace")
                                     if name in ("name", "text", "audio") else getattr(event, name))
                               for name, _ in Event._fields_})
            if count < len(data):
                return result

    def snapshot(self):
        if self._journal is not None:
            return self._snapshot_prefix + zlib.compress(self._journal, 1)
        count = self.lib.rsp_snapshot(self.handle, None)
        data = C.create_string_buffer(count * self.lib.rsp_track_size())
        self.lib.rsp_snapshot(self.handle, data)
        return data.raw

    def restore(self, data):
        if self._journal is not None:
            if not data.startswith(self._snapshot_prefix):
                raise ValueError('Spine snapshot version or source asset differs')
            replacement = None
            try:
                journal = zlib.decompress(data[len(self._snapshot_prefix):])
                replacement = Native(self.lib, *self._source)
                replacement._replaying = True
                offset = 0
                allowed = {'default_mix', 'mix', 'play', 'clear', 'skin', 'empty', 'override'}
                while offset < len(journal):
                    size, = struct.unpack_from('<I', journal, offset)
                    offset += 4
                    if size == 0:
                        delta, = struct.unpack_from('<f', journal, offset)
                        offset += 4
                        replacement.update(delta)
                        replacement.events()
                    elif size == 1:
                        replacement.draw()
                    else:
                        if size > len(journal) - offset:
                            raise ValueError('Truncated Spine snapshot')
                        operation, args = json.loads(journal[offset:offset + size])
                        offset += size
                        if operation not in allowed:
                            raise ValueError('Unknown Spine snapshot operation')
                        if operation == 'override':
                            replacement.override(args[0], **args[1])
                        else:
                            getattr(replacement, operation)(*args)
                replacement.events()
            except (ValueError, TypeError, IndexError, KeyError, AttributeError,
                    OverflowError, struct.error, zlib.error) as error:
                if replacement:
                    replacement.close()
                raise ValueError('Invalid Spine animation snapshot') from error
            # Swap only after complete validation and replay. Failed restores
            # leave the live skeleton and its physics simulation untouched.
            self.close()
            self.handle, replacement.handle = replacement.handle, None
            self.overrides = replacement.overrides
            self._journal = bytearray(journal)
            return
        size = self.lib.rsp_track_size()
        if len(data) % size or not self.lib.rsp_restore(self.handle, data, len(data) // size):
            raise ValueError("Invalid Spine animation snapshot")
