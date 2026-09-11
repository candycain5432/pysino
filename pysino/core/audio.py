"""Procedurally synthesised sound effects.

Every sound is generated as raw 16-bit PCM the first time it is asked for, so
Pysino ships no audio files.  If there is no usable audio device - a headless
machine, a CI runner, a locked sound card - the whole module quietly degrades
to doing nothing rather than taking the game down with it.
"""

from __future__ import annotations

import array
import math
import random
from typing import Callable, Dict, Iterable, Optional

import pygame

RATE = 44_100
_MAX = 32_767


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _blank(samples: int) -> array.array:
    return array.array("h", bytes(2 * samples))


def _envelope(t: float, duration: float, attack: float, release: float) -> float:
    """Linear attack into a squared decay; cheap but sounds natural enough."""
    if t < attack:
        return t / attack if attack else 1.0
    remaining = duration - attack
    if remaining <= 0:
        return 0.0
    fade = 1.0 - (t - attack) / max(1e-6, min(release, remaining))
    return max(0.0, fade) ** 2


def tone(
    frequency: float,
    duration: float,
    volume: float = 0.4,
    wave: str = "sine",
    attack: float = 0.005,
    release: Optional[float] = None,
    sweep: float = 0.0,
) -> array.array:
    """A single enveloped oscillator.  ``sweep`` bends the pitch over time."""
    count = max(1, int(RATE * duration))
    out = _blank(count)
    release = duration if release is None else release
    phase = 0.0
    for index in range(count):
        t = index / RATE
        current = frequency * (1.0 + sweep * (t / max(1e-6, duration)))
        phase += 2 * math.pi * current / RATE
        if wave == "square":
            value = 1.0 if math.sin(phase) >= 0 else -1.0
        elif wave == "saw":
            value = (phase / math.pi) % 2 - 1
        elif wave == "triangle":
            value = 2 * abs((phase / math.pi) % 2 - 1) - 1
        else:
            value = math.sin(phase)
        out[index] = int(_clamp(value * _envelope(t, duration, attack, release) * volume) * _MAX)
    return out


def noise(
    duration: float,
    volume: float = 0.3,
    attack: float = 0.002,
    release: Optional[float] = None,
    smoothing: float = 0.0,
    seed: int = 0,
) -> array.array:
    """White noise, optionally low-passed to sound more like a rustle."""
    count = max(1, int(RATE * duration))
    out = _blank(count)
    release = duration if release is None else release
    rng = random.Random(seed)
    previous = 0.0
    for index in range(count):
        t = index / RATE
        sample = rng.uniform(-1.0, 1.0)
        if smoothing:
            sample = previous + (sample - previous) * (1.0 - smoothing)
            previous = sample
        out[index] = int(_clamp(sample * _envelope(t, duration, attack, release) * volume) * _MAX)
    return out


def silence(duration: float) -> array.array:
    return _blank(max(1, int(RATE * duration)))


def mix(*layers: array.array) -> array.array:
    """Sum several buffers, clipping the result."""
    length = max((len(layer) for layer in layers), default=0)
    out = _blank(length)
    for layer in layers:
        for index, sample in enumerate(layer):
            total = out[index] + sample
            out[index] = max(-_MAX, min(_MAX, total))
    return out


def chain(*parts: array.array) -> array.array:
    out = array.array("h")
    for part in parts:
        out.extend(part)
    return out


def arpeggio(frequencies: Iterable[float], step: float = 0.08, volume: float = 0.35,
             wave: str = "sine") -> array.array:
    return chain(*(tone(freq, step * 1.6, volume, wave, release=step * 1.6)
                   for freq in frequencies))


# ------------------------------------------------------------- the library --
#: Note frequencies used to build the musical cues.
C5, D5, E5, G5, A5, C6, E6, G6 = 523.25, 587.33, 659.25, 783.99, 880.0, 1046.5, 1318.5, 1568.0

RECIPES: Dict[str, Callable[[], array.array]] = {
    "click": lambda: tone(1_400, 0.035, 0.25, "square", release=0.03),
    "select": lambda: tone(880, 0.06, 0.22, "triangle", release=0.055),
    "back": lambda: tone(420, 0.08, 0.22, "triangle", release=0.075),
    "chip": lambda: mix(
        tone(2_200, 0.04, 0.18, "square", release=0.035),
        noise(0.05, 0.10, smoothing=0.55, seed=3),
    ),
    "deal": lambda: noise(0.09, 0.20, smoothing=0.72, seed=7),
    "flip": lambda: noise(0.07, 0.16, smoothing=0.6, seed=11),
    "shuffle": lambda: noise(0.45, 0.14, smoothing=0.82, seed=13),
    "win": lambda: arpeggio((C5, E5, G5, C6), 0.075, 0.33),
    "bigwin": lambda: chain(
        arpeggio((C5, E5, G5, C6, E6), 0.07, 0.34),
        mix(tone(G6, 0.5, 0.28, release=0.5), tone(C6, 0.5, 0.22, release=0.5)),
    ),
    "jackpot": lambda: chain(
        arpeggio((C5, E5, G5, C6, E6, G6), 0.06, 0.34),
        arpeggio((G6, E6, C6, G5), 0.05, 0.30),
        mix(tone(C6, 0.7, 0.30, release=0.7), tone(E6, 0.7, 0.24, release=0.7)),
    ),
    "lose": lambda: chain(
        tone(220, 0.14, 0.28, "triangle", release=0.13),
        tone(160, 0.26, 0.26, "triangle", release=0.25),
    ),
    "push": lambda: tone(392, 0.18, 0.24, "triangle", release=0.17),
    "cash": lambda: mix(
        arpeggio((A5, C6, E6), 0.06, 0.30),
        noise(0.18, 0.06, smoothing=0.5, seed=21),
    ),
    "spin": lambda: noise(0.55, 0.12, smoothing=0.88, seed=29, release=0.5),
    "reel": lambda: tone(600, 0.05, 0.22, "square", release=0.045),
    "tick": lambda: tone(1_800, 0.02, 0.14, "square", release=0.018),
    "bomb": lambda: mix(
        noise(0.45, 0.34, smoothing=0.5, seed=31, release=0.44),
        tone(90, 0.4, 0.30, "triangle", release=0.38, sweep=-0.5),
    ),
    "gem": lambda: arpeggio((E6, G6), 0.05, 0.26, "triangle"),
    "crash": lambda: mix(
        noise(0.35, 0.30, smoothing=0.4, seed=37),
        tone(140, 0.35, 0.26, "saw", release=0.33, sweep=-0.6),
    ),
    "launch": lambda: tone(200, 0.5, 0.22, "triangle", release=0.45, sweep=2.0),
    "ball": lambda: tone(1_100, 0.03, 0.16, "square", release=0.025),
    "achievement": lambda: chain(
        arpeggio((G5, C6, E6, G6), 0.06, 0.32, "triangle"),
    ),
}


class Audio:
    """Lazily builds and plays the sound library."""

    def __init__(self, enabled: bool = True, volume: float = 0.5) -> None:
        self.enabled = enabled
        self._volume = max(0.0, min(1.0, volume))
        self.available = False
        self._cache: Dict[str, pygame.mixer.Sound] = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=RATE, size=-16, channels=1, buffer=512)
            self.available = pygame.mixer.get_init() is not None
        except pygame.error:
            # No audio device: keep going in silence.
            self.available = False

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, value))
        for sound in self._cache.values():
            sound.set_volume(self._volume)

    def _sound(self, name: str) -> Optional[pygame.mixer.Sound]:
        if not self.available:
            return None
        cached = self._cache.get(name)
        if cached is not None:
            return cached
        recipe = RECIPES.get(name)
        if recipe is None:
            return None
        try:
            sound = pygame.mixer.Sound(buffer=recipe().tobytes())
        except (pygame.error, ValueError):
            return None
        sound.set_volume(self._volume)
        self._cache[name] = sound
        return sound

    def play(self, name: str, volume: Optional[float] = None) -> None:
        """Play a named effect; unknown names and dead devices are ignored."""
        if not self.enabled or not self.available:
            return
        sound = self._sound(name)
        if sound is None:
            return
        if volume is not None:
            sound.set_volume(max(0.0, min(1.0, volume * self._volume)))
        try:
            sound.play()
        except pygame.error:
            pass

    def preload(self, names: Iterable[str] = ()) -> None:
        """Build sounds up front so the first play does not stutter."""
        for name in (names or RECIPES.keys()):
            self._sound(name)

    def stop(self) -> None:
        if self.available:
            pygame.mixer.stop()
