"""Scene base class and the stack that switches between them."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

import pygame

from . import render, theme
from .ui import Widget

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..app import App


class Scene:
    """One screen of the game.

    Subclasses draw onto the fixed-size canvas and receive mouse positions that
    have already been converted into canvas coordinates.
    """

    #: Shown in the top bar.
    title = "Pysino"
    subtitle = ""
    #: Set False for screens that paint their own full-bleed header.
    show_hud = True
    #: Escape returns to the lobby unless a scene wants to handle it itself.
    escape_returns = True
    #: Identifier used for bank statistics; None for non-game screens.
    game_key: Optional[str] = None

    def __init__(self, app: "App") -> None:
        self.app = app
        self.widgets: List[Widget] = []
        self.time = 0.0

    # ------------------------------------------------------- conveniences --
    @property
    def bank(self):
        return self.app.bank

    @property
    def rng(self):
        return self.app.rng

    @property
    def audio(self):
        return self.app.audio

    @property
    def fonts(self):
        return theme.fonts()

    @property
    def particles(self):
        return self.app.particles

    def toast(self, message: str, color=theme.GOLD, duration: float = 2.6) -> None:
        self.app.toasts.push(message, color, duration=duration)

    def add(self, widget: Widget) -> Widget:
        self.widgets.append(widget)
        return widget

    def clear_widgets(self) -> None:
        self.widgets.clear()

    # ---------------------------------------------------------- lifecycle --
    def on_enter(self, **kwargs) -> None:
        """Called every time the scene becomes the active one."""

    def on_exit(self) -> None:
        """Called when the scene is left; a good place to persist state."""

    # ------------------------------------------------------------- events --
    def handle_event(self, event: pygame.event.Event) -> bool:
        for widget in reversed(self.widgets):
            if widget.handle_event(event):
                return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.escape_returns:
                self.app.go_to("lobby")
                return True
        return False

    def update(self, dt: float, mouse_pos: Tuple[int, int]) -> None:
        self.time += dt
        for widget in self.widgets:
            widget.update(dt, mouse_pos)

    def draw(self, surface: pygame.Surface) -> None:
        self.draw_background(surface)
        self.draw_content(surface)
        self.draw_widgets(surface)

    def draw_background(self, surface: pygame.Surface) -> None:
        render.felt_table(surface)
        render.vignette(surface, 160)

    def draw_content(self, surface: pygame.Surface) -> None:
        """Scene-specific drawing goes here."""

    def draw_widgets(self, surface: pygame.Surface) -> None:
        for widget in self.widgets:
            widget.draw(surface)


class SceneStack:
    """Holds the active scene and applies switches between frames.

    Switching is deferred so a scene can safely ask for a change from inside
    its own event handling without the stack changing under its feet.
    """

    def __init__(self) -> None:
        self._stack: List[Scene] = []
        self._pending: Optional[Tuple[str, Scene, dict]] = None

    @property
    def current(self) -> Optional[Scene]:
        return self._stack[-1] if self._stack else None

    @property
    def depth(self) -> int:
        return len(self._stack)

    def push(self, scene: Scene, **kwargs) -> None:
        self._pending = ("push", scene, kwargs)

    def replace(self, scene: Scene, **kwargs) -> None:
        self._pending = ("replace", scene, kwargs)

    def pop(self) -> None:
        self._pending = ("pop", None, {})

    def apply_pending(self) -> bool:
        """Carry out a deferred switch.  Returns True when something changed."""
        if self._pending is None:
            return False
        action, scene, kwargs = self._pending
        self._pending = None

        if action == "pop":
            if self._stack:
                self._stack.pop().on_exit()
            if self._stack:
                self._stack[-1].on_enter()
            return True

        if action == "replace" and self._stack:
            self._stack.pop().on_exit()
        elif action == "push" and self._stack:
            # The scene underneath stays alive but stops receiving updates.
            pass

        assert scene is not None
        self._stack.append(scene)
        scene.on_enter(**kwargs)
        return True

    def clear(self) -> None:
        while self._stack:
            self._stack.pop().on_exit()
