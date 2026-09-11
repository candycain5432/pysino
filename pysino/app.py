"""The application shell: window, main loop, scene switching and the HUD.

Everything is drawn onto a fixed 1280x720 canvas which is then scaled and
letterboxed into whatever window the player has.  Mouse positions are converted
back into canvas space before reaching scenes, so all layout code can use plain
absolute coordinates.
"""

from __future__ import annotations

import os
import random
from typing import Callable, Dict, Optional, Tuple

import pygame

from . import config
from .core import render, theme
from .core.audio import Audio
from .core.bank import Bank
from .core.particles import ParticleSystem
from .core.rng import ProvablyFairRandom, new_server_seed
from .core.scene import Scene, SceneStack
from .core.ui import ToastStack, ValueTicker

HUD_HEIGHT = 56


class App:
    """Owns the window, the shared services and the scene stack."""

    def __init__(self, start_scene: str = "lobby", headless: bool = False) -> None:
        if headless:
            # A dummy video driver still gives us a display surface, which the
            # renderer needs in order to convert() its cached artwork.
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        pygame.init()
        self._clear_render_caches()
        self.headless = headless
        self.bank = Bank.load()

        if headless:
            try:
                self.window = pygame.display.set_mode(config.BASE_SIZE)
            except pygame.error:
                self.window = pygame.Surface(config.BASE_SIZE)
        else:
            self.window = pygame.display.set_mode(config.BASE_SIZE, pygame.RESIZABLE)
            pygame.display.set_caption(config.WINDOW_TITLE)
            self._set_icon()

        self.canvas = pygame.Surface(config.BASE_SIZE)
        if pygame.display.get_surface() is not None:
            self.canvas = self.canvas.convert()
        self.clock = pygame.time.Clock()
        self.running = False
        self.dt = 0.0

        seed = str(self.bank.fair.get("server_seed") or "") or new_server_seed()
        self.bank.fair["server_seed"] = seed
        self.rng = ProvablyFairRandom(
            server_seed=seed,
            client_seed=str(self.bank.fair.get("client_seed") or "pysino"),
            nonce=int(self.bank.fair.get("nonce") or 0),
        )

        self.audio = Audio(
            enabled=bool(self.bank.settings.get("sfx", True)),
            volume=float(self.bank.settings.get("volume", 0.5)),
        )
        self.particles = ParticleSystem(random.Random())
        self.toasts = ToastStack((config.BASE_WIDTH - 16, HUD_HEIGHT + 12))
        self.chip_ticker = ValueTicker(self.bank.chips)

        self.scenes = SceneStack()
        self._factories: Dict[str, Callable[[App], Scene]] = {}
        self._register_scenes()

        self._scale = 1.0
        self._offset = (0, 0)
        self._recompute_transform()

        self._fade = 0.0
        self._fade_target = 0.0
        self._pending_scene: Optional[Tuple[str, dict]] = None
        self.show_fps = False

        self.bank.subscribe(self._on_bank_change)
        self.go_to(start_scene, instant=True)

    # ------------------------------------------------------------- set-up --
    @staticmethod
    def _clear_render_caches() -> None:
        """Start from cold caches.

        Fonts and converted surfaces built before a previous ``pygame.quit()``
        are dead handles, so a second :class:`App` in the same process must not
        inherit them.
        """
        from .core import cardrender, slotart

        theme.clear_cache()
        render.clear_cache()
        cardrender.clear_cache()
        slotart.clear_cache()

    def _set_icon(self) -> None:
        icon = pygame.Surface((32, 32), pygame.SRCALPHA)
        pygame.draw.circle(icon, theme.GOLD, (16, 16), 15)
        pygame.draw.circle(icon, theme.FELT_DARK, (16, 16), 10)
        from .core.cardrender import draw_pip

        draw_pip(icon, pygame.Rect(9, 8, 14, 16), "s", theme.GOLD_BRIGHT)
        pygame.display.set_icon(icon)

    def _register_scenes(self) -> None:
        """Scene modules are imported lazily to keep start-up snappy."""
        from .scenes import (
            blackjack, crash, holdem, lobby, mines, roulette, settings, slots,
            stats, videopoker,
        )

        self._factories = {
            "lobby": lobby.LobbyScene,
            "blackjack": blackjack.BlackjackScene,
            "holdem": holdem.HoldemScene,
            "slots": slots.SlotsScene,
            "mines": mines.MinesScene,
            "roulette": roulette.RouletteScene,
            "videopoker": videopoker.VideoPokerScene,
            "crash": crash.CrashScene,
            "stats": stats.StatsScene,
            "settings": settings.SettingsScene,
        }

    @property
    def scene_names(self):
        return tuple(self._factories)

    # ------------------------------------------------------- scene switch --
    def go_to(self, name: str, instant: bool = False, **kwargs) -> None:
        """Fade out, swap to ``name``, fade back in."""
        if name not in self._factories:
            raise KeyError(f"unknown scene: {name}")
        if instant:
            self._swap(name, kwargs)
            self._fade = 0.0
            self._fade_target = 0.0
            return
        self._pending_scene = (name, kwargs)
        self._fade_target = 1.0

    def _swap(self, name: str, kwargs: dict) -> None:
        scene = self._factories[name](self)
        self.scenes.replace(scene, **kwargs)
        self.scenes.apply_pending()

    # -------------------------------------------------------- coordinates --
    def _recompute_transform(self) -> None:
        width, height = self.window.get_size()
        self._scale = min(width / config.BASE_WIDTH, height / config.BASE_HEIGHT)
        shown = (config.BASE_WIDTH * self._scale, config.BASE_HEIGHT * self._scale)
        self._offset = ((width - shown[0]) / 2, (height - shown[1]) / 2)

    def to_canvas(self, position: Tuple[float, float]) -> Tuple[int, int]:
        """Window coordinates to canvas coordinates."""
        scale = self._scale or 1.0
        return (
            int((position[0] - self._offset[0]) / scale),
            int((position[1] - self._offset[1]) / scale),
        )

    @property
    def mouse_pos(self) -> Tuple[int, int]:
        return self.to_canvas(pygame.mouse.get_pos())

    # ------------------------------------------------------------- events --
    def _on_bank_change(self, reason: str, delta: int) -> None:
        self.chip_ticker.set(self.bank.chips)
        for achievement in list(self.bank.pending_achievements):
            self.toasts.push(
                f"{achievement.icon}  {achievement.name}", theme.GOLD, duration=3.4
            )
            self.audio.play("achievement")
        self.bank.pending_achievements.clear()

    def _translate(self, event: pygame.event.Event) -> pygame.event.Event:
        """Rewrite mouse positions into canvas space before dispatching."""
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            data = dict(event.dict)
            data["pos"] = self.to_canvas(event.pos)
            return pygame.event.Event(event.type, data)
        return event

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.quit()
            return
        if event.type == pygame.VIDEORESIZE:
            self._recompute_transform()
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                self.toggle_fullscreen()
                return
            if event.key == pygame.K_F3:
                self.show_fps = not self.show_fps
                return

        scene = self.scenes.current
        if scene and self._fade_target == 0.0:
            scene.handle_event(self._translate(event))

    def toggle_fullscreen(self) -> None:
        if self.headless:
            return
        self.bank.settings["fullscreen"] = not bool(self.bank.settings.get("fullscreen"))
        if self.bank.settings["fullscreen"]:
            self.window = pygame.display.set_mode(config.BASE_SIZE, pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode(config.BASE_SIZE, pygame.RESIZABLE)
        self._recompute_transform()

    # ------------------------------------------------------------- update --
    def update(self, dt: float) -> None:
        self.dt = dt
        mouse = self.mouse_pos

        # Drive the cross-fade, swapping scenes while the screen is dark.
        speed = 4.5
        if self._fade < self._fade_target:
            self._fade = min(self._fade_target, self._fade + dt * speed)
            if self._fade >= 1.0 and self._pending_scene:
                name, kwargs = self._pending_scene
                self._pending_scene = None
                self._swap(name, kwargs)
                self._fade_target = 0.0
        elif self._fade > self._fade_target:
            self._fade = max(self._fade_target, self._fade - dt * speed)

        scene = self.scenes.current
        if scene:
            scene.update(dt, mouse)
        self.particles.update(dt)
        self.toasts.update(dt, mouse)
        self.chip_ticker.update(dt)

    # --------------------------------------------------------------- draw --
    def draw(self) -> None:
        scene = self.scenes.current
        if scene:
            scene.draw(self.canvas)
            if scene.show_hud:
                self.draw_hud(self.canvas, scene)
        self.particles.draw(self.canvas)
        self.toasts.draw(self.canvas)

        if self._fade > 0.001:
            veil = pygame.Surface(config.BASE_SIZE, pygame.SRCALPHA)
            veil.fill(theme.with_alpha(theme.BG_DEEP, int(255 * self._fade)))
            self.canvas.blit(veil, (0, 0))

        if self.show_fps:
            render.text(
                self.canvas, theme.fonts().tiny(bold=True),
                f"{self.clock.get_fps():.0f} fps", (8, config.BASE_HEIGHT - 8),
                theme.TEXT_MUTED, anchor="bottomleft",
            )
        self._present()

    def _present(self) -> None:
        if self.headless:
            return
        width, height = self.window.get_size()
        target = (max(1, int(config.BASE_WIDTH * self._scale)),
                  max(1, int(config.BASE_HEIGHT * self._scale)))
        self.window.fill(theme.BG_DEEP)
        if target == config.BASE_SIZE:
            self.window.blit(self.canvas, self._offset)
        else:
            self.window.blit(pygame.transform.smoothscale(self.canvas, target), self._offset)
        pygame.display.flip()

    def draw_hud(self, surface: pygame.Surface, scene: Scene) -> None:
        """The persistent top bar: where you are, and what you are worth."""
        bar = pygame.Rect(0, 0, config.BASE_WIDTH, HUD_HEIGHT)
        render.gradient(surface, bar, theme.BG_RAISED, theme.PANEL)
        pygame.draw.line(surface, theme.GOLD_DIM, (0, HUD_HEIGHT - 1),
                         (config.BASE_WIDTH, HUD_HEIGHT - 1), 1)

        fonts = theme.fonts()
        render.text(surface, fonts.body(bold=True), scene.title, (20, 16), theme.TEXT)
        if scene.subtitle:
            offset = fonts.body(bold=True).size(scene.title)[0] + 32
            render.text(surface, fonts.small(), scene.subtitle, (offset, 20), theme.TEXT_DIM)

        from .core.cardrender import chip_surface

        # Right-align the stack, then hang the chip icon off its left edge, so a
        # seven figure balance still cannot run off the bar.
        amount = f"{self.chip_ticker.value:,}"
        amount_rect = render.text(
            surface, fonts.large(bold=True), amount,
            (config.BASE_WIDTH - 20, HUD_HEIGHT // 2), theme.GOLD, anchor="midright",
        )
        chip = chip_surface(100, 15)
        surface.blit(chip, chip.get_rect(center=(amount_rect.left - 20, HUD_HEIGHT // 2)))

        if scene.escape_returns:
            hint_x = 20 + fonts.body(bold=True).size(scene.title)[0] + 20
            if scene.subtitle:
                hint_x += fonts.small().size(scene.subtitle)[0] + 24
            render.text(surface, fonts.tiny(), "ESC  lobby", (hint_x, HUD_HEIGHT // 2 + 1),
                        theme.TEXT_MUTED, anchor="midleft")

    # --------------------------------------------------------------- loop --
    def run(self) -> None:
        self.running = True
        while self.running:
            self.dt = min(self.clock.tick(config.FPS) / 1000.0, 0.05)
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(self.dt)
            self.draw()
        self.shutdown()

    def step(self, dt: float = 1 / 60) -> None:
        """Advance one frame without a window; used by the smoke tests."""
        self.update(dt)
        self.draw()

    def quit(self) -> None:
        self.running = False

    def save(self) -> None:
        self.bank.fair["client_seed"] = self.rng.client_seed
        self.bank.fair["nonce"] = self.rng.nonce
        self.bank.fair["server_seed"] = self.rng.server_seed
        self.bank.settings["sfx"] = self.audio.enabled
        self.bank.settings["volume"] = self.audio.volume
        self.bank.save()

    def shutdown(self) -> None:
        scene = self.scenes.current
        if scene:
            scene.on_exit()
        self.save()
        pygame.quit()
