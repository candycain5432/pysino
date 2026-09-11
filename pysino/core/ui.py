"""Widget toolkit: buttons, toggles, sliders, text fields, toasts and chip rails.

Widgets receive mouse positions already converted into canvas space by the
application, so they can work in the fixed 1280x720 coordinate system no matter
how the window has been resized.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pygame

from . import anim, render, theme

Color = Tuple[int, int, int]

# ------------------------------------------------------------------ styles --
PRIMARY = "primary"
SECONDARY = "secondary"
SUCCESS = "success"
DANGER = "danger"
GHOST = "ghost"

_STYLES: Dict[str, Dict[str, Color]] = {
    PRIMARY: {"fill": theme.GOLD, "edge": theme.GOLD_BRIGHT, "text": theme.INK},
    SECONDARY: {"fill": theme.PANEL_LIGHT, "edge": theme.PANEL_EDGE, "text": theme.TEXT},
    SUCCESS: {"fill": (36, 128, 78), "edge": (72, 184, 118), "text": theme.TEXT},
    DANGER: {"fill": (150, 44, 42), "edge": (216, 82, 76), "text": theme.TEXT},
    GHOST: {"fill": (0, 0, 0), "edge": theme.PANEL_EDGE, "text": theme.TEXT_DIM},
}


class Widget:
    """Base class: a rect that can take events, animate and draw itself."""

    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = pygame.Rect(rect)
        self.visible = True
        self.enabled = True

    @property
    def interactive(self) -> bool:
        return self.visible and self.enabled

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True when the event was consumed."""
        return False

    def update(self, dt: float, mouse_pos: Tuple[int, int]) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pass


class Button(Widget):
    """A clickable button with hover/press feedback and an optional hotkey."""

    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        on_click: Optional[Callable[[], None]] = None,
        style: str = SECONDARY,
        hotkey: Optional[int] = None,
        hotkey_label: str = "",
        font: Optional[pygame.font.Font] = None,
        sublabel: str = "",
        radius: int = 10,
    ) -> None:
        super().__init__(rect)
        self.label = label
        self.sublabel = sublabel
        self.on_click = on_click
        self.style = style
        self.hotkey = hotkey
        self.hotkey_label = hotkey_label
        self.font = font
        self.radius = radius
        self.hovered = False
        self.pressed = False
        self._hover_amount = 0.0
        self._flash = 0.0

    # ------------------------------------------------------------- events --
    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.interactive:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_pressed, self.pressed = self.pressed, False
            if was_pressed and self.rect.collidepoint(event.pos):
                self.activate()
                return True
        elif event.type == pygame.KEYDOWN and self.hotkey and event.key == self.hotkey:
            self.activate()
            return True
        return False

    def activate(self) -> None:
        self._flash = 1.0
        if self.on_click:
            self.on_click()

    def update(self, dt: float, mouse_pos: Tuple[int, int]) -> None:
        self.hovered = self.interactive and self.rect.collidepoint(mouse_pos)
        target = 1.0 if self.hovered else 0.0
        self._hover_amount += (target - self._hover_amount) * min(1.0, dt * 14)
        self._flash = max(0.0, self._flash - dt * 3.5)

    # --------------------------------------------------------------- draw --
    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        palette = _STYLES.get(self.style, _STYLES[SECONDARY])
        rect = self.rect.copy()
        if self.pressed and self.hovered:
            rect.y += 2

        fill = palette["fill"]
        edge = palette["edge"]
        text_color = palette["text"]

        if not self.enabled:
            fill = theme.darken(fill, 0.55)
            edge = theme.darken(edge, 0.55)
            text_color = theme.TEXT_MUTED
        else:
            fill = theme.lighten(fill, 0.10 * self._hover_amount + 0.25 * self._flash)
            if self.style == GHOST:
                fill = theme.mix(theme.PANEL, theme.PANEL_LIGHT, self._hover_amount)

        if self.enabled and self._hover_amount > 0.01 and self.style == PRIMARY:
            render.glow(surface, rect, theme.GOLD, self.radius,
                        spread=10, alpha=int(70 * self._hover_amount))

        render.drop_shadow(surface, rect, radius=self.radius, spread=4, alpha=70)
        render.rounded_rect(surface, rect, fill, self.radius)
        render.rounded_rect(surface, rect, edge, self.radius, width=1)

        font = self.font or theme.fonts().body(bold=True)
        centre = rect.center if not self.sublabel else (rect.centerx, rect.centery - 8)
        render.text(surface, font, self.label, centre, text_color, anchor="center")
        if self.sublabel:
            render.text(
                surface, theme.fonts().tiny(), self.sublabel,
                (rect.centerx, rect.centery + 12),
                theme.mix(text_color, theme.PANEL, 0.35), anchor="center",
            )
        if self.hotkey_label and self.enabled:
            badge = theme.fonts().tiny(bold=True)
            render.text(
                surface, badge, self.hotkey_label,
                (rect.right - 7, rect.top + 5),
                theme.mix(text_color, fill, 0.45), anchor="topright",
            )


class ToggleButton(Button):
    """A button that latches on and off."""

    def __init__(self, *args, value: bool = False, on_change=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.value = value
        self.on_change = on_change

    def activate(self) -> None:
        self.value = not self.value
        self._flash = 1.0
        if self.on_change:
            self.on_change(self.value)
        if self.on_click:
            self.on_click()

    def draw(self, surface: pygame.Surface) -> None:
        self.style = PRIMARY if self.value else GHOST
        super().draw(surface)


class Slider(Widget):
    """A horizontal slider over an integer or float range."""

    def __init__(
        self,
        rect: pygame.Rect,
        minimum: float,
        maximum: float,
        value: float,
        on_change: Optional[Callable[[float], None]] = None,
        step: float = 0.0,
        label: str = "",
        formatter: Optional[Callable[[float], str]] = None,
    ) -> None:
        super().__init__(rect)
        self.minimum = minimum
        self.maximum = maximum
        self.value = value
        self.on_change = on_change
        self.step = step
        self.label = label
        self.formatter = formatter or (lambda v: f"{v:.0f}")
        self.dragging = False

    @property
    def fraction(self) -> float:
        span = self.maximum - self.minimum
        return (self.value - self.minimum) / span if span else 0.0

    def _set_from_x(self, x: int) -> None:
        track = self._track()
        fraction = anim.clamp((x - track.x) / max(1, track.width), 0.0, 1.0)
        value = self.minimum + fraction * (self.maximum - self.minimum)
        if self.step:
            value = round(value / self.step) * self.step
        value = anim.clamp(value, self.minimum, self.maximum)
        if value != self.value:
            self.value = value
            if self.on_change:
                self.on_change(value)

    def _track(self) -> pygame.Rect:
        return pygame.Rect(self.rect.x + 10, self.rect.centery - 3, self.rect.width - 20, 6)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.interactive:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.dragging = True
                self._set_from_x(event.pos[0])
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = False
                return True
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._set_from_x(event.pos[0])
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        track = self._track()
        render.rounded_rect(surface, track, theme.PANEL, 3)
        filled = pygame.Rect(track.x, track.y, int(track.width * self.fraction), track.height)
        render.rounded_rect(surface, filled, theme.GOLD, 3)
        knob = (track.x + int(track.width * self.fraction), track.centery)
        render.circle(surface, knob, 9, theme.GOLD_BRIGHT)
        render.circle(surface, knob, 9, theme.GOLD_DIM, 1)
        if self.label:
            render.text(surface, theme.fonts().tiny(), self.label,
                        (self.rect.x, self.rect.y - 4), theme.TEXT_DIM, anchor="bottomleft")
        render.text(surface, theme.fonts().tiny(bold=True), self.formatter(self.value),
                    (self.rect.right, self.rect.y - 4), theme.TEXT, anchor="bottomright")


class TextInput(Widget):
    """A single-line text field, used for the provably-fair client seed."""

    def __init__(
        self,
        rect: pygame.Rect,
        value: str = "",
        placeholder: str = "",
        max_length: int = 48,
        on_submit: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(rect)
        self.value = value
        self.placeholder = placeholder
        self.max_length = max_length
        self.on_submit = on_submit
        self.focused = False
        self._caret = 0.0

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.interactive:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focused = self.rect.collidepoint(event.pos)
            return self.focused
        if not self.focused or event.type != pygame.KEYDOWN:
            return False
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.focused = False
            if self.on_submit:
                self.on_submit(self.value)
        elif event.key == pygame.K_BACKSPACE:
            self.value = self.value[:-1]
        elif event.key == pygame.K_ESCAPE:
            self.focused = False
        elif event.unicode and event.unicode.isprintable():
            if len(self.value) < self.max_length:
                self.value += event.unicode
        return True

    def update(self, dt: float, mouse_pos: Tuple[int, int]) -> None:
        self._caret = (self._caret + dt) % 1.0

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        edge = theme.GOLD if self.focused else theme.PANEL_EDGE
        render.rounded_rect(surface, self.rect, theme.BG_DEEP, 8)
        render.rounded_rect(surface, self.rect, edge, 8, width=1)
        font = theme.fonts().small(mono=True) if False else theme.fonts().small()
        shown = self.value or self.placeholder
        color = theme.TEXT if self.value else theme.TEXT_MUTED
        glyphs = font.render(shown, True, color)
        clip = surface.get_clip()
        surface.set_clip(self.rect.inflate(-16, -4))
        surface.blit(glyphs, (self.rect.x + 10, self.rect.centery - glyphs.get_height() // 2))
        if self.focused and self._caret < 0.5:
            caret_x = self.rect.x + 12 + font.size(self.value)[0]
            pygame.draw.line(
                surface, theme.GOLD,
                (caret_x, self.rect.centery - 9), (caret_x, self.rect.centery + 9), 2,
            )
        surface.set_clip(clip)


# ------------------------------------------------------------------ toasts --
@dataclass
class Toast:
    message: str
    color: Color = theme.GOLD
    icon: str = ""
    duration: float = 2.6
    elapsed: float = 0.0

    @property
    def done(self) -> bool:
        return self.elapsed >= self.duration

    @property
    def alpha(self) -> int:
        fade_in = anim.clamp(self.elapsed / 0.2, 0.0, 1.0)
        fade_out = anim.clamp((self.duration - self.elapsed) / 0.4, 0.0, 1.0)
        return int(255 * min(fade_in, fade_out))


class ToastStack(Widget):
    """Transient messages stacked in a corner."""

    def __init__(self, anchor: Tuple[int, int] = (1264, 92), width: int = 380) -> None:
        super().__init__(pygame.Rect(anchor[0] - width, anchor[1], width, 10))
        self.anchor = anchor
        self.width = width
        self.toasts: List[Toast] = []

    def push(self, message: str, color: Color = theme.GOLD, icon: str = "",
             duration: float = 2.6) -> None:
        self.toasts.append(Toast(message, color, icon, duration))
        if len(self.toasts) > 5:
            self.toasts.pop(0)

    def update(self, dt: float, mouse_pos: Tuple[int, int]) -> None:
        for toast in self.toasts:
            toast.elapsed += dt
        self.toasts = [toast for toast in self.toasts if not toast.done]

    def draw(self, surface: pygame.Surface) -> None:
        font = theme.fonts().small(bold=True)
        y = self.anchor[1]
        for toast in self.toasts:
            text_width = font.size(toast.message)[0]
            box = pygame.Rect(0, 0, min(self.width, text_width + 62), 40)
            box.topright = (self.anchor[0], y)
            layer = pygame.Surface(box.size, pygame.SRCALPHA)
            local = layer.get_rect()
            render.rounded_rect(layer, local, theme.with_alpha(theme.PANEL, 236), 10)
            render.rounded_rect(layer, local, theme.with_alpha(toast.color, 255), 10, width=1)
            pygame.draw.rect(layer, toast.color, pygame.Rect(0, 0, 4, local.height),
                             border_top_left_radius=10, border_bottom_left_radius=10)
            render.text(layer, font, toast.message, (16, local.centery),
                        theme.TEXT, anchor="midleft")
            layer.set_alpha(toast.alpha)
            surface.blit(layer, box.topleft)
            y += box.height + 8


# --------------------------------------------------------------- chip rail --
class ChipRail(Widget):
    """A row of chip denominations for building a bet."""

    def __init__(
        self,
        position: Tuple[int, int],
        denominations: Sequence[int],
        on_pick: Callable[[int], None],
        radius: int = 26,
        spacing: int = 12,
    ) -> None:
        width = len(denominations) * (radius * 2 + spacing) - spacing
        super().__init__(pygame.Rect(position[0], position[1], width, radius * 2))
        self.denominations = list(denominations)
        self.on_pick = on_pick
        self.radius = radius
        self.spacing = spacing
        self.selected: Optional[int] = denominations[0] if denominations else None
        self.affordable: Callable[[int], bool] = lambda amount: True
        self._hover: Optional[int] = None

    def _centre(self, index: int) -> Tuple[int, int]:
        step = self.radius * 2 + self.spacing
        return (self.rect.x + self.radius + index * step, self.rect.centery)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.interactive:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, denomination in enumerate(self.denominations):
                centre = self._centre(index)
                if math.dist(event.pos, centre) <= self.radius:
                    if self.affordable(denomination):
                        self.selected = denomination
                        self.on_pick(denomination)
                        return True
        return False

    def update(self, dt: float, mouse_pos: Tuple[int, int]) -> None:
        self._hover = None
        for index, denomination in enumerate(self.denominations):
            if math.dist(mouse_pos, self._centre(index)) <= self.radius:
                self._hover = denomination

    def draw(self, surface: pygame.Surface) -> None:
        from . import cardrender

        for index, denomination in enumerate(self.denominations):
            centre = self._centre(index)
            usable = self.affordable(denomination)
            lift = 6 if denomination == self._hover and usable else 0
            if denomination == self.selected:
                render.circle(surface, (centre[0], centre[1] - lift),
                              self.radius + 4, theme.GOLD_BRIGHT)
            chip = cardrender.chip_surface(denomination, self.radius)
            if not usable:
                chip = chip.copy()
                chip.set_alpha(70)
            surface.blit(chip, chip.get_rect(center=(centre[0], centre[1] - lift)))


class ValueTicker:
    """A number that animates towards its target instead of snapping."""

    def __init__(self, value: int = 0, rate: float = 6.0) -> None:
        self.target = int(value)
        self.shown = float(value)
        self.rate = rate

    def set(self, value: int, immediate: bool = False) -> None:
        self.target = int(value)
        if immediate:
            self.shown = float(value)

    def update(self, dt: float) -> None:
        gap = self.target - self.shown
        if abs(gap) < 0.6:
            self.shown = float(self.target)
            return
        self.shown += gap * min(1.0, dt * self.rate)

    @property
    def value(self) -> int:
        return int(round(self.shown))

    @property
    def moving(self) -> bool:
        return self.shown != float(self.target)


# ------------------------------------------------------------------ layout --
def button_row(
    x: int,
    y: int,
    width: int,
    height: int,
    count: int,
    gap: int = 10,
) -> List[pygame.Rect]:
    """Evenly spaced rects for a horizontal run of buttons."""
    return [pygame.Rect(x + index * (width + gap), y, width, height) for index in range(count)]


def centred_row(
    centre_x: int,
    y: int,
    width: int,
    height: int,
    count: int,
    gap: int = 10,
) -> List[pygame.Rect]:
    total = count * width + (count - 1) * gap
    start = centre_x - total // 2
    return button_row(start, y, width, height, count, gap)
