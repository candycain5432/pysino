"""Shared behaviour for the betting games.

:class:`GameScene` wires a scene up to the shared chip bank: it moves chips in
and out, books the result for the statistics screen, celebrates wins and offers
a top-up when the player runs dry.  :class:`BetControls` is the stake selector
that every game puts on its felt.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

import pygame

from .. import config
from ..core import anim, cardrender, render, theme, ui
from ..core.bank import InsufficientChips
from ..core.scene import Scene


class GameScene(Scene):
    """A scene that takes bets."""

    game_key: Optional[str] = None
    min_bet = config.MIN_BET
    #: Default stake the first time a player sits down at this game.
    default_bet = 25

    def __init__(self, app) -> None:
        super().__init__(app)
        self.bet = self._remembered_bet()
        self.last_result_text = ""
        self.last_result_color = theme.TEXT

    # --------------------------------------------------------------- bets --
    def _remembered_bet(self) -> int:
        remembered = self.app.bank.settings.get(f"bet_{self.game_key}")
        try:
            value = int(remembered)
        except (TypeError, ValueError):
            value = self.default_bet
        return max(self.min_bet, value)

    def remember_bet(self) -> None:
        if self.game_key:
            self.app.bank.settings[f"bet_{self.game_key}"] = int(self.bet)

    def on_exit(self) -> None:
        self.remember_bet()
        self.app.save()

    @property
    def max_bet(self) -> int:
        return max(self.min_bet, min(config.MAX_BET, self.bank.chips))

    def clamp_bet(self, amount: int) -> int:
        return max(self.min_bet, min(int(amount), self.max_bet))

    def can_afford(self, amount: Optional[int] = None) -> bool:
        return self.bank.can_afford(self.bet if amount is None else amount)

    # ------------------------------------------------------------- chips --
    def wager(self, amount: int) -> bool:
        """Take ``amount`` off the stack.  False when the player cannot pay."""
        if self.game_key is None:
            raise RuntimeError("a betting scene needs a game_key")
        try:
            self.bank.wager(self.game_key, amount)
        except InsufficientChips:
            self.toast("Not enough chips", theme.LOSE)
            self.audio.play("back")
            return False
        self.audio.play("chip")
        return True

    def award(self, amount: int) -> int:
        if amount > 0 and self.game_key:
            self.bank.award(self.game_key, amount)
        return amount

    def settle(
        self,
        staked: int,
        returned: int,
        *,
        celebrate_at: Tuple[int, int] = (config.BASE_WIDTH // 2, 360),
        quiet: bool = False,
    ) -> int:
        """Book a finished round and react to the outcome."""
        if self.game_key is None:
            raise RuntimeError("a betting scene needs a game_key")
        net = self.bank.finish_round(self.game_key, staked, returned)
        if quiet:
            return net

        if net > 0:
            self.last_result_text = f"+{net:,}"
            self.last_result_color = theme.WIN
            big = staked and net >= staked * 5
            self.audio.play("bigwin" if big else "win")
            if big:
                self.particles.confetti(celebrate_at, count=70)
            else:
                self.particles.coins(celebrate_at, count=26)
        elif net < 0:
            self.last_result_text = f"{net:,}"
            self.last_result_color = theme.LOSE
            self.audio.play("lose")
        else:
            self.last_result_text = "Push"
            self.last_result_color = theme.PUSH
            self.audio.play("push")
        return net

    # ----------------------------------------------------------- broke UI --
    @property
    def is_broke(self) -> bool:
        return self.bank.chips < self.min_bet

    def draw_bailout_prompt(self, surface: pygame.Surface) -> None:
        """Offered when the player cannot cover the table minimum."""
        box = pygame.Rect(0, 0, 460, 190)
        box.center = (config.BASE_WIDTH // 2, config.BASE_HEIGHT // 2)
        render.panel(surface, box, theme.PANEL, theme.LOSE, radius=16)
        render.text(surface, self.fonts.large(bold=True), "Out of chips",
                    (box.centerx, box.y + 46), theme.TEXT, anchor="center")
        render.text(
            surface, self.fonts.small(),
            f"The house will stake you {config.BAILOUT_CHIPS:,} chips.",
            (box.centerx, box.y + 84), theme.TEXT_DIM, anchor="center",
        )


class BetControls:
    """Chip rail plus the usual clear/half/double/max shortcuts."""

    def __init__(
        self,
        scene: GameScene,
        position: Tuple[int, int],
        on_change: Optional[Callable[[int], None]] = None,
        denominations: Sequence[int] = config.CHIP_DENOMINATIONS,
        show_rail: bool = True,
        label: str = "BET",
    ) -> None:
        self.scene = scene
        self.position = position
        self.on_change = on_change
        self.label = label
        self.enabled = True
        x, y = position

        self.rail: Optional[ui.ChipRail] = None
        if show_rail:
            self.rail = ui.ChipRail((x, y + 44), denominations, self._add, radius=24)
            self.rail.affordable = lambda amount: scene.bank.chips >= amount
            scene.add(self.rail)

        rail_width = self.rail.rect.width if self.rail else 240
        buttons = ui.button_row(x, y + 100, (rail_width - 30) // 4, 30, 4, gap=10)
        specs = [
            ("Clear", self._clear),
            ("1/2", self._halve),
            ("x2", self._double),
            ("Max", self._max),
        ]
        self.buttons: List[ui.Button] = []
        for rect, (text, action) in zip(buttons, specs):
            button = ui.Button(rect, text, action, ui.GHOST, font=theme.fonts().tiny(bold=True),
                               radius=6)
            self.buttons.append(button)
            scene.add(button)

        self.rect = pygame.Rect(x, y, rail_width, 130)

    # ------------------------------------------------------------ actions --
    def _emit(self) -> None:
        self.scene.audio.play("chip")
        if self.on_change:
            self.on_change(self.scene.bet)

    def _add(self, amount: int) -> None:
        self.scene.bet = self.scene.clamp_bet(self.scene.bet + amount)
        self._emit()

    def _clear(self) -> None:
        self.scene.bet = self.scene.min_bet
        self._emit()

    def _halve(self) -> None:
        self.scene.bet = self.scene.clamp_bet(self.scene.bet // 2)
        self._emit()

    def _double(self) -> None:
        self.scene.bet = self.scene.clamp_bet(self.scene.bet * 2)
        self._emit()

    def _max(self) -> None:
        self.scene.bet = self.scene.max_bet
        self._emit()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if self.rail:
            self.rail.enabled = enabled
        for button in self.buttons:
            button.enabled = enabled

    # --------------------------------------------------------------- draw --
    def draw(self, surface: pygame.Surface) -> None:
        fonts = theme.fonts()
        x, y = self.position
        render.text(surface, fonts.tiny(bold=True), self.label, (x, y),
                    theme.TEXT_MUTED if not self.enabled else theme.TEXT_DIM)
        colour = theme.GOLD if self.enabled else theme.TEXT_MUTED
        render.text(surface, fonts.large(bold=True), f"{self.scene.bet:,}",
                    (x, y + 14), colour)


def draw_result_banner(
    surface: pygame.Surface,
    message: str,
    color,
    centre: Tuple[int, int],
    subtitle: str = "",
    width: int = 380,
) -> pygame.Rect:
    """The big 'you won' / 'you lost' plate."""
    box = pygame.Rect(0, 0, width, 84 if subtitle else 62)
    box.center = centre
    render.glow(surface, box, color, radius=14, spread=18, alpha=90)
    render.panel(surface, box, theme.PANEL, color, radius=14)
    fonts = theme.fonts()
    if subtitle:
        render.text(surface, fonts.large(bold=True), message,
                    (box.centerx, box.y + 28), color, anchor="center")
        render.text(surface, fonts.small(), subtitle,
                    (box.centerx, box.y + 60), theme.TEXT_DIM, anchor="center")
    else:
        render.text(surface, fonts.large(bold=True), message, box.center,
                    color, anchor="center")
    return box


def draw_stat_row(
    surface: pygame.Surface,
    rect: pygame.Rect,
    label: str,
    value: str,
    value_color=theme.TEXT,
) -> None:
    fonts = theme.fonts()
    render.text(surface, fonts.small(), label, (rect.x, rect.centery),
                theme.TEXT_DIM, anchor="midleft")
    render.text(surface, fonts.small(bold=True), value, (rect.right, rect.centery),
                value_color, anchor="midright")


class CardFlight:
    """Animates cards travelling from the shoe to wherever they are dealt.

    Scenes describe the layout they *want* each frame via :meth:`sync`; cards
    that are new fly in from the shoe with a staggered delay, cards that moved
    (a split shifting a hand sideways) glide to their new home, and cards that
    vanished are dropped.
    """

    def __init__(
        self,
        origin: Tuple[int, int],
        duration: float = 0.30,
        stagger: float = 0.10,
        flip_duration: float = 0.26,
    ) -> None:
        self.origin = origin
        self.duration = duration
        self.stagger = stagger
        self.flip_duration = flip_duration
        self._cards: dict = {}
        self._queue_time = 0.0

    def reset(self) -> None:
        self._cards.clear()
        self._queue_time = 0.0

    def sync(self, targets) -> None:
        """``targets`` is an ordered sequence of ``(key, position, face_up)``."""
        seen = set()
        for key, position, face_up in targets:
            seen.add(key)
            entry = self._cards.get(key)
            if entry is None:
                delay = max(0.0, self._queue_time)
                self._queue_time += self.stagger
                self._cards[key] = {
                    "tween": anim.Tween(self.origin, position, self.duration,
                                        anim.ease_out_cubic, delay),
                    "face_up": face_up,
                    "flip": 0.0 if face_up else None,
                    "position": self.origin,
                }
            else:
                current = entry["position"]
                if abs(current[0] - position[0]) > 1 or abs(current[1] - position[1]) > 1:
                    if entry["tween"].done:
                        entry["tween"] = anim.Tween(current, position, 0.22,
                                                    anim.ease_out_cubic)
                    else:
                        entry["tween"].end = position
                if face_up and entry["face_up"] is False:
                    entry["face_up"] = True
                    entry["flip"] = 0.0
                elif not face_up:
                    entry["face_up"] = False
        for key in [key for key in self._cards if key not in seen]:
            del self._cards[key]
        if not self._cards:
            self._queue_time = 0.0

    def update(self, dt: float) -> None:
        self._queue_time = max(0.0, self._queue_time - dt)
        for entry in self._cards.values():
            entry["tween"].update(dt)
            entry["position"] = entry["tween"].value
            if entry["flip"] is not None and entry["flip"] < 1.0:
                entry["flip"] = min(1.0, entry["flip"] + dt / self.flip_duration)

    @property
    def busy(self) -> bool:
        return any(not entry["tween"].done for entry in self._cards.values())

    def has(self, key) -> bool:
        return key in self._cards

    def draw_card(
        self,
        surface: pygame.Surface,
        key,
        card,
        size: Tuple[int, int],
        highlight=None,
        dim: bool = False,
    ) -> Optional[pygame.Rect]:
        """Draw one tracked card at its animated position."""
        entry = self._cards.get(key)
        if entry is None:
            return None
        position = entry["position"]
        face_up = entry["face_up"]
        flip = entry["flip"]

        if face_up and flip is not None and flip < 1.0:
            sprite, offset = cardrender.flipped_card(card, flip, size)
            rect = sprite.get_rect(topleft=(int(position[0]) + offset, int(position[1])))
            render.drop_shadow(surface, rect, radius=6, spread=4, alpha=90)
            surface.blit(sprite, rect)
            return rect

        rect = cardrender.draw_card(
            surface, card if face_up else None, (int(position[0]), int(position[1])),
            size, face_up=face_up, highlight=highlight,
        )
        if dim:
            veil = pygame.Surface(size, pygame.SRCALPHA)
            veil.fill(theme.with_alpha(theme.BG_DEEP, 120))
            surface.blit(veil, rect.topleft)
        return rect
