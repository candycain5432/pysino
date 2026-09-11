"""Easing curves, tweens and small timed sequences.

Scenes describe motion declaratively - "move this card here over 0.3s" - and
let :class:`Animator` advance everything once per frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple


# ------------------------------------------------------------------ easing --
def linear(t: float) -> float:
    return t


def ease_in_quad(t: float) -> float:
    return t * t


def ease_out_quad(t: float) -> float:
    return 1.0 - (1.0 - t) ** 2


def ease_in_out_quad(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


def ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
    """Overshoots the target then settles - good for things landing."""
    c3 = overshoot + 1
    return 1 + c3 * (t - 1) ** 3 + overshoot * (t - 1) ** 2


def ease_out_elastic(t: float) -> float:
    if t in (0.0, 1.0):
        return t
    period = 2 * math.pi / 3
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * period) + 1


def ease_out_bounce(t: float) -> float:
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


EASINGS = {
    "linear": linear,
    "in_quad": ease_in_quad,
    "out_quad": ease_out_quad,
    "in_out_quad": ease_in_out_quad,
    "out_cubic": ease_out_cubic,
    "in_out_cubic": ease_in_out_cubic,
    "out_back": ease_out_back,
    "out_elastic": ease_out_elastic,
    "out_bounce": ease_out_bounce,
}


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_point(a: Sequence[float], b: Sequence[float], t: float) -> Tuple[float, float]:
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ------------------------------------------------------------------ tweens --
@dataclass
class Tween:
    """Interpolates a scalar (or point) from ``start`` to ``end``."""

    start: float | Tuple[float, float]
    end: float | Tuple[float, float]
    duration: float
    easing: Callable[[float], float] = ease_out_cubic
    delay: float = 0.0
    on_complete: Optional[Callable[[], None]] = None
    elapsed: float = 0.0
    _fired: bool = False

    @property
    def progress(self) -> float:
        if self.elapsed <= self.delay:
            return 0.0
        if self.duration <= 0:
            return 1.0
        return clamp((self.elapsed - self.delay) / self.duration, 0.0, 1.0)

    @property
    def done(self) -> bool:
        return self.elapsed >= self.delay + self.duration

    @property
    def value(self):
        t = self.easing(self.progress)
        if isinstance(self.start, tuple):
            return lerp_point(self.start, self.end, t)
        return lerp(self.start, self.end, t)

    def update(self, dt: float) -> None:
        self.elapsed += dt
        if self.done and not self._fired:
            self._fired = True
            if self.on_complete:
                self.on_complete()

    def reset(self) -> None:
        self.elapsed = 0.0
        self._fired = False


@dataclass
class Animator:
    """Owns a bag of tweens and advances them together."""

    tweens: List[Tween] = field(default_factory=list)

    def add(self, tween: Tween) -> Tween:
        self.tweens.append(tween)
        return tween

    def update(self, dt: float) -> None:
        for tween in list(self.tweens):
            tween.update(dt)
            if tween.done:
                self.tweens.remove(tween)

    @property
    def busy(self) -> bool:
        return bool(self.tweens)

    def clear(self) -> None:
        self.tweens.clear()


@dataclass
class Timeline:
    """Fires callbacks at set offsets - handy for staged deals and reveals."""

    _events: List[Tuple[float, Callable[[], None]]] = field(default_factory=list)
    elapsed: float = 0.0

    def at(self, when: float, callback: Callable[[], None]) -> "Timeline":
        self._events.append((when, callback))
        self._events.sort(key=lambda item: item[0])
        return self

    def update(self, dt: float) -> None:
        self.elapsed += dt
        while self._events and self._events[0][0] <= self.elapsed:
            _, callback = self._events.pop(0)
            callback()

    @property
    def done(self) -> bool:
        return not self._events

    def clear(self) -> None:
        self._events.clear()
        self.elapsed = 0.0


def pulse(time: float, speed: float = 3.0, low: float = 0.0, high: float = 1.0) -> float:
    """A smooth 0-1 oscillation, for breathing highlights."""
    return low + (high - low) * (0.5 + 0.5 * math.sin(time * speed))
