"""A small particle system for confetti, coin showers and sparks."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import pygame

from . import theme

GRAVITY = 900.0


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: Tuple[int, int, int]
    size: float
    spin: float = 0.0
    angle: float = 0.0
    shape: str = "rect"
    gravity: float = GRAVITY
    drag: float = 0.0

    @property
    def alive(self) -> bool:
        return self.life > 0.0

    def update(self, dt: float) -> None:
        self.life -= dt
        self.vy += self.gravity * dt
        if self.drag:
            self.vx *= (1.0 - self.drag * dt)
            self.vy *= (1.0 - self.drag * dt)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt

    def draw(self, surface: pygame.Surface) -> None:
        fade = max(0.0, min(1.0, self.life / self.max_life))
        alpha = int(255 * fade)
        if self.shape == "circle":
            layer = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                layer, theme.with_alpha(self.color, alpha),
                (self.size, self.size), max(1, int(self.size)),
            )
            surface.blit(layer, (self.x - self.size, self.y - self.size))
            return
        width = max(2.0, self.size)
        height = max(2.0, self.size * 0.6)
        layer = pygame.Surface((width, height), pygame.SRCALPHA)
        layer.fill(theme.with_alpha(self.color, alpha))
        rotated = pygame.transform.rotate(layer, math.degrees(self.angle))
        surface.blit(rotated, rotated.get_rect(center=(self.x, self.y)))


class ParticleSystem:
    """Holds live particles; scenes call :meth:`update` then :meth:`draw`."""

    #: Hard ceiling so a pathological win can never tank the frame rate.
    MAX_PARTICLES = 600

    def __init__(self, rng: random.Random | None = None) -> None:
        self.particles: List[Particle] = []
        self.rng = rng or random.Random()

    def __len__(self) -> int:
        return len(self.particles)

    @property
    def active(self) -> bool:
        return bool(self.particles)

    def clear(self) -> None:
        self.particles.clear()

    def _add(self, particle: Particle) -> None:
        if len(self.particles) < self.MAX_PARTICLES:
            self.particles.append(particle)

    def confetti(self, position: Sequence[float], count: int = 60,
                 colors: Sequence[Tuple[int, int, int]] | None = None,
                 spread: float = 260.0) -> None:
        """A celebratory burst that rains down."""
        palette = colors or (theme.GOLD, theme.GOLD_BRIGHT, theme.WIN, theme.INFO,
                             theme.PURPLE, theme.TEXT)
        for _ in range(count):
            angle = self.rng.uniform(-math.pi, 0)
            speed = self.rng.uniform(spread * 0.4, spread)
            self._add(Particle(
                x=position[0] + self.rng.uniform(-20, 20),
                y=position[1],
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                life=self.rng.uniform(1.0, 2.0),
                max_life=2.0,
                color=self.rng.choice(palette),
                size=self.rng.uniform(6, 12),
                spin=self.rng.uniform(-10, 10),
                angle=self.rng.uniform(0, math.pi),
            ))

    def coins(self, position: Sequence[float], count: int = 30) -> None:
        """Gold discs tumbling upward then falling - a payout."""
        for _ in range(count):
            self._add(Particle(
                x=position[0] + self.rng.uniform(-30, 30),
                y=position[1],
                vx=self.rng.uniform(-160, 160),
                vy=self.rng.uniform(-520, -260),
                life=self.rng.uniform(0.9, 1.6),
                max_life=1.6,
                color=self.rng.choice((theme.GOLD, theme.GOLD_BRIGHT, theme.SILVER)),
                size=self.rng.uniform(5, 9),
                shape="circle",
            ))

    def sparks(self, position: Sequence[float], count: int = 24,
               color: Tuple[int, int, int] = theme.GOLD_BRIGHT) -> None:
        """A quick radial flash with no gravity - impacts and reveals."""
        for _ in range(count):
            angle = self.rng.uniform(0, math.tau)
            speed = self.rng.uniform(90, 320)
            self._add(Particle(
                x=position[0], y=position[1],
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                life=self.rng.uniform(0.25, 0.6),
                max_life=0.6,
                color=color,
                size=self.rng.uniform(3, 6),
                shape="circle",
                gravity=0.0,
                drag=3.0,
            ))

    def smoke(self, position: Sequence[float], count: int = 18,
              color: Tuple[int, int, int] = (90, 90, 96)) -> None:
        """Rising puffs, used when a mine goes off."""
        for _ in range(count):
            self._add(Particle(
                x=position[0] + self.rng.uniform(-14, 14),
                y=position[1] + self.rng.uniform(-10, 10),
                vx=self.rng.uniform(-50, 50),
                vy=self.rng.uniform(-140, -40),
                life=self.rng.uniform(0.5, 1.1),
                max_life=1.1,
                color=color,
                size=self.rng.uniform(8, 16),
                shape="circle",
                gravity=-40.0,
                drag=1.5,
            ))

    def update(self, dt: float) -> None:
        for particle in self.particles:
            particle.update(dt)
        self.particles = [particle for particle in self.particles if particle.alive]

    def draw(self, surface: pygame.Surface) -> None:
        for particle in self.particles:
            particle.draw(surface)
