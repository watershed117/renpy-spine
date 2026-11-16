"""Bone-space touch regions and transient, smoothed pointer control for Spine."""
import math
import weakref
from collections import namedtuple

import pygame_sdl2 as pygame
import renpy
import renpy.exports as exports
from renpy.display.displayable import Displayable
from renpy.display.render import Render


TouchRegion = namedtuple("TouchRegion", "name bone radius center press release tracks",
                         defaults=((0.0, 0.0), (), (), (3, 4)))
PointerBinding = namedtuple("PointerBinding", "bone reference radius limits mode center regions",
                            defaults=("hover", (0.0, 0.0), ()))
_states = weakref.WeakKeyDictionary()


class _Settings(renpy.python.RevertableObject):
    def __init__(self):
        self.touch = True
        self.follow = True
        self.debug = False


class _State:
    def __init__(self):
        self.point = None
        self.pressed = None
        self.drag_start = {}
        self.values = {}
        self.last_st = None
        self.events = []


class SpineInteraction(Displayable):
    """Wrap ``actor`` with input in its own canvas coordinate system.

    TouchRegion ellipses follow their named animated bone. Press/release contain
    animation names, paired with tracks; release animations automatically fade
    out. PointerBinding drives dedicated control bones in reference-bone space.
    Pointer positions and held buttons are transient, while settings roll back.
    Input events are polled separately from the actor's exported Spine events.
    """
    def __init__(self, actor, regions=(), bindings=(), smoothing=0.09, **properties):
        super().__init__(**properties)
        self.actor = actor
        self.regions, self.bindings = tuple(regions), tuple(bindings)
        self.smoothing = float(smoothing)
        if not math.isfinite(self.smoothing) or self.smoothing < 0:
            raise ValueError("Pointer smoothing must be finite and nonnegative")
        bones, animations = set(actor.bones), set(actor.animations)
        for item in self.regions + self.bindings:
            if item.bone not in bones:
                raise ValueError("Unknown interaction bone: " + item.bone)
            if len(item.radius) != 2 or not all(math.isfinite(v) and v > 0 for v in item.radius):
                raise ValueError("Interaction radii must be finite and positive")
            if len(item.center) != 2 or not all(math.isfinite(v) for v in item.center):
                raise ValueError("Interaction centers must be finite pairs")
        for region in self.regions:
            if len(region.press) > len(region.tracks) or len(region.release) > len(region.tracks):
                raise ValueError("Each touch animation needs its own track")
            if any(name not in animations for name in region.press + region.release):
                raise ValueError("Unknown touch animation")
            if any(not isinstance(track, int) or not 0 <= track <= 31 for track in region.tracks):
                raise ValueError("Touch tracks must be between 0 and 31")
        for binding in self.bindings:
            if binding.reference not in bones or binding.mode not in ("hover", "drag"):
                raise ValueError("Invalid pointer reference or mode")
            if len(binding.limits) != 2 or not all(math.isfinite(v) and v >= 0 for v in binding.limits):
                raise ValueError("Pointer limits must be finite and nonnegative")
        if len({b.bone for b in self.bindings}) != len(self.bindings):
            raise ValueError("A pointer control bone may only have one binding")
        self.settings = _Settings()
        self._release_on_load = None

    def _state(self):
        state = _states.get(self)
        if state is None:
            state = _State()
            _states[self] = state
        return state

    def hit_test(self, x, y):
        if not (0 <= x < self.actor.size[0] and 0 <= y < self.actor.size[1]):
            return None
        for region in self.regions:
            point = self.actor.canvas_to_bone(region.bone, x, y)
            if point and sum(((p - c) / r) ** 2 for p, c, r in zip(point, region.center, region.radius)) <= 1:
                return region
        return None

    def _emit(self, kind, region, point):
        state = self._state()
        state.events.append({"type": kind, "region": region.name,
                             "position": point})
        del state.events[:-128]

    def _play_region(self, region, release=False):
        names = region.release if release else region.press
        for track, name in zip(region.tracks, names):
            self.actor.play(name, track=track, loop=False)
            if release:
                duration = self.actor.animations[name]
                self.actor.queue_empty(track=track, mix=0.12, delay=max(duration, 0.001))
        if release:
            for track in region.tracks[len(names):len(region.press)]:
                self.actor.clear(track=track, mix=0.12)

    def _release(self, kind="release"):
        state = self._state()
        region = state.pressed
        if region is not None:
            self._play_region(region, release=True)
            self._emit(kind, region, state.point)
            state.pressed = None
            state.drag_start.clear()

    def cancel(self):
        """End held gestures before opening menus, changing actors or hiding."""
        self._release("cancel")
        state = self._state()
        state.point = None
        state.values.clear()
        state.last_st = None
        self.actor._pointer_bones({})
        exports.redraw(self, 0)

    def set_touch(self, enabled):
        self.settings.touch = bool(enabled)
        if not enabled:
            self._release("cancel")

    def set_follow(self, enabled):
        self.settings.follow = bool(enabled)
        if not enabled:
            state = self._state()
            for binding in self.bindings:
                if binding.mode == "hover":
                    state.values.pop(binding.bone, None)
            self._update_pointer(state.last_st or 0.0)

    def set_debug(self, enabled):
        self.settings.debug = bool(enabled)
        exports.redraw(self, 0)

    def input_events(self):
        state = self._state()
        events, state.events = state.events, []
        return events

    def _update_pointer(self, st):
        state = self._state()
        delta = 1.0 / self.actor.fps if state.last_st is None else max(0.0, min(st - state.last_st, 0.1))
        state.last_st = st
        if self.actor.control.paused:
            return
        weight = 1.0 if self.smoothing == 0 else -math.expm1(-delta / self.smoothing)
        output = {}
        for binding in self.bindings:
            target = (0.0, 0.0)
            active = (self.settings.follow if binding.mode == "hover" else
                      state.pressed is not None and (not binding.regions or state.pressed.name in binding.regions))
            if active and state.point is not None:
                point = self.actor.canvas_to_bone(binding.reference, *state.point)
                if point is not None:
                    center = ((state.drag_start.get(binding.bone) or point)
                              if binding.mode == "drag" else binding.center)
                    target = tuple(max(-1.0, min(1.0, (p - c) / r)) * limit
                                   for p, c, r, limit in zip(point, center, binding.radius, binding.limits))
            old = state.values.get(binding.bone, (0.0, 0.0))
            value = tuple(a + (b - a) * weight for a, b in zip(old, target))
            if max(abs(v) for v in value) > 0.001:
                state.values[binding.bone] = value
                output[binding.bone] = dict(zip(("x", "y"), value))
            else:
                state.values.pop(binding.bone, None)
        if output or self.actor._session().pointer_overrides:
            self.actor._pointer_bones(output)
            exports.redraw(self, 0)

    def event(self, ev, x, y, st):
        state = self._state()
        focus_lost = (ev.type == getattr(pygame, "WINDOWFOCUSLOST", -1) or
                      ev.type == getattr(pygame, "WINDOWLEAVE", -1) or
                      (ev.type == pygame.ACTIVEEVENT and not getattr(ev, "gain", True)))
        if focus_lost or exports.map_event(ev, "game_menu"):
            self.cancel()
            return None
        pointer_event = ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)
        had_press = state.pressed is not None
        inside = 0 <= x < self.actor.size[0] and 0 <= y < self.actor.size[1]
        if not inside:
            state.point = None
            self._release("cancel")
        if pointer_event:
            state.point = (float(x), float(y)) if inside else None
            if not inside:
                self._release("cancel")
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                region = self.hit_test(x, y) if self.settings.touch and not self.actor.control.paused else None
                if region is not None:
                    self._release("cancel")
                    state.pressed = region
                    state.drag_start = {b.bone: self.actor.canvas_to_bone(b.reference, x, y)
                                        for b in self.bindings if b.mode == "drag"}
                    self._play_region(region)
                    self._emit("press", region, state.point)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                held = had_press
                self._release()
                if getattr(ev, "touch", False):
                    state.point = None
                self._update_pointer(st)
                if held:
                    raise renpy.display.core.IgnoreEvent()
        # Ren'Py normalizes a primary finger to mouse events with local x/y.
        # A timer also notices a release consumed by a control above this actor.
        if state.pressed is not None and not pointer_event and not pygame.mouse.get_pressed()[0]:
            self._release("cancel")
        self._update_pointer(st)
        if self.bindings:
            exports.timeout(1.0 / self.actor.fps)
        if pointer_event and state.pressed is not None:
            raise renpy.display.core.IgnoreEvent()
        return None

    def per_interact(self):
        # A loaded save cannot retain a held finger. Ordinary screen restarts
        # (for example updating a status label) must preserve an active drag.
        if self._release_on_load is not None:
            self._play_region(self._release_on_load, release=True)
            self._release_on_load = None
            self.cancel()
        exports.redraw(self, 0)
        if self.bindings:
            exports.timeout(1.0 / self.actor.fps)

    def visit(self):
        return [self.actor]

    def render(self, width, height, st, at):
        result = Render(*self.actor.size)
        result.blit(exports.render(self.actor, width, height, st, at), (0, 0))
        if self.settings.debug:
            canvas = result.canvas()
            state = self._state()
            for region in self.regions:
                points = [self.actor.bone_to_canvas(region.bone,
                          region.center[0] + region.radius[0] * math.cos(i * math.tau / 48),
                          region.center[1] + region.radius[1] * math.sin(i * math.tau / 48))
                          for i in range(48)]
                canvas.lines("#ffcf67" if state.pressed == region else "#67ddff", True, points, 2)
            if not self.actor.control.paused:
                exports.redraw(self, 1.0 / self.actor.fps)
        return result

    def __getstate__(self):
        state = super().__getstate__()
        live = _states.get(self)
        if live is not None:
            state["_release_on_load"] = live.pressed
        return state
