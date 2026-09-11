"""Settings, plus the provably-fair panel where seeds can be checked."""

from __future__ import annotations

import pygame

from .. import config
from ..core import render, theme, ui
from ..core.scene import Scene


class SettingsScene(Scene):
    title = "Settings"
    subtitle = "Sound, display and verifiable randomness"

    def __init__(self, app) -> None:
        super().__init__(app)
        self.last_reveal = None
        self._build_widgets()

    def _build_widgets(self) -> None:
        self.sfx_toggle = ui.ToggleButton(
            pygame.Rect(60, 160, 170, 44), "Sound", None, ui.GHOST,
            value=self.audio.enabled, on_change=self._toggle_sfx,
        )
        self.add(self.sfx_toggle)

        self.volume_slider = ui.Slider(
            pygame.Rect(60, 244, 300, 32), 0.0, 1.0, self.audio.volume,
            self._set_volume, step=0.05, label="Volume",
            formatter=lambda value: f"{int(value * 100)}%",
        )
        self.add(self.volume_slider)

        self.add(ui.Button(
            pygame.Rect(60, 312, 170, 44), "Fullscreen", self.app.toggle_fullscreen,
            ui.SECONDARY, pygame.K_F11, "F11",
        ))

        self.seed_input = ui.TextInput(
            pygame.Rect(660, 304, 400, 38), self.app.rng.client_seed,
            "your client seed", on_submit=self._set_client_seed,
        )
        self.add(self.seed_input)

        self.add(ui.Button(
            pygame.Rect(660, 352, 190, 40), "Apply seed",
            lambda: self._set_client_seed(self.seed_input.value), ui.SECONDARY,
        ))
        self.add(ui.Button(
            pygame.Rect(866, 352, 194, 40), "Rotate server seed",
            self._rotate, ui.PRIMARY, font=self.fonts.small(bold=True),
        ))

        self.add(ui.Button(
            pygame.Rect(60, 560, 230, 44), "Reset profile", self._reset, ui.DANGER,
        ))
        self.add(ui.Button(
            pygame.Rect(config.BASE_WIDTH - 180, config.BASE_HEIGHT - 62, 140, 44),
            "Back", lambda: self.app.go_to("lobby"), ui.SECONDARY, pygame.K_b, "B",
        ))

    # ------------------------------------------------------------ actions --
    def _toggle_sfx(self, value: bool) -> None:
        self.audio.enabled = value
        self.bank.settings["sfx"] = value
        if value:
            self.audio.play("select")

    def _set_volume(self, value: float) -> None:
        self.audio.volume = value
        self.bank.settings["volume"] = value

    def _set_client_seed(self, value: str) -> None:
        seed = value.strip() or "pysino"
        self.app.rng.set_client_seed(seed)
        self.bank.fair["client_seed"] = seed
        self.app.toasts.push("Client seed updated", theme.GOLD)
        self.audio.play("select")

    def _rotate(self) -> None:
        self.last_reveal = self.app.rng.rotate_server_seed()
        self.bank.fair["server_seed"] = self.app.rng.server_seed
        self.bank.fair["nonce"] = 0
        self.app.toasts.push("Server seed rotated", theme.GOLD, duration=3.2)
        self.audio.play("select")

    def _reset(self) -> None:
        from ..core.bank import Bank

        self.app.bank = Bank()
        self.app.chip_ticker.set(self.app.bank.chips, immediate=True)
        self.app.bank.subscribe(self.app._on_bank_change)
        self.app.save()
        self.app.toasts.push("Profile reset", theme.LOSE)
        self.audio.play("back")

    # --------------------------------------------------------------- draw --
    def draw_background(self, surface: pygame.Surface) -> None:
        render.gradient(surface, surface.get_rect(), (16, 30, 44), theme.BG_DEEP)
        render.vignette(surface, 160)

    def draw_content(self, surface: pygame.Surface) -> None:
        left = pygame.Rect(30, 96, 580, 560)
        render.panel(surface, left, theme.PANEL, theme.PANEL_EDGE, radius=14)
        render.text(surface, self.fonts.body(bold=True), "Audio and display",
                    (left.x + 30, left.y + 20), theme.GOLD)
        render.text(surface, self.fonts.tiny(),
                    "F11 toggles fullscreen at any time.  F3 shows the frame rate.",
                    (left.x + 30, left.y + 274), theme.TEXT_MUTED)

        render.text(surface, self.fonts.body(bold=True), "Danger zone",
                    (left.x + 30, left.y + 400), theme.LOSE)
        render.text(surface, self.fonts.tiny(),
                    "Wipes chips, statistics and achievements. There is no undo.",
                    (left.x + 30, left.y + 428), theme.TEXT_MUTED)

        self._draw_fair_panel(surface)

    def _draw_fair_panel(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(630, 96, config.BASE_WIDTH - 660, 560)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=14)
        render.text(surface, self.fonts.body(bold=True), "Provably fair",
                    (box.x + 30, box.y + 20), theme.GOLD)
        render.text_wrapped(
            surface, self.fonts.tiny(),
            "Every outcome comes from HMAC-SHA512 over the server seed, your client "
            "seed and a round counter. The hash below commits the house to a server "
            "seed it cannot change. Rotate it to reveal the old seed and check any "
            "round you have played.",
            pygame.Rect(box.x + 30, box.y + 46, box.width - 60, 80), theme.TEXT_DIM,
        )

        render.text(surface, self.fonts.tiny(bold=True), "SERVER SEED HASH",
                    (box.x + 30, box.y + 132), theme.TEXT_MUTED)
        self._draw_hash(surface, self.app.rng.commitment, (box.x + 30, box.y + 150),
                        box.width - 60)

        render.text(surface, self.fonts.tiny(bold=True), "CLIENT SEED",
                    (box.x + 30, box.y + 190), theme.TEXT_MUTED)

        render.text(surface, self.fonts.tiny(bold=True), "ROUNDS ON THIS SEED",
                    (box.x + 30, box.y + 306), theme.TEXT_MUTED)
        render.text(surface, self.fonts.body(bold=True), f"{self.app.rng.nonce:,}",
                    (box.x + 30, box.y + 324), theme.TEXT)

        if self.last_reveal:
            reveal = self.last_reveal
            panel = pygame.Rect(box.x + 24, box.y + 362, box.width - 48, 182)
            render.panel(surface, panel, theme.BG_DEEP, theme.GOLD_DIM, radius=10)
            render.text(surface, self.fonts.tiny(bold=True), "REVEALED SEED",
                        (panel.x + 16, panel.y + 12), theme.GOLD)
            self._draw_hash(surface, reveal.server_seed, (panel.x + 16, panel.y + 32),
                            panel.width - 32)
            render.text(surface, self.fonts.tiny(bold=True), "ITS COMMITMENT",
                        (panel.x + 16, panel.y + 78), theme.TEXT_MUTED)
            self._draw_hash(surface, reveal.commitment, (panel.x + 16, panel.y + 96),
                            panel.width - 32)
            verified = reveal.verify()
            render.text(
                surface, self.fonts.small(bold=True),
                "verified: the hash matches" if verified else "MISMATCH",
                (panel.x + 16, panel.bottom - 28),
                theme.WIN if verified else theme.LOSE,
            )
            render.text(surface, self.fonts.tiny(), f"covered {reveal.rounds:,} rounds",
                        (panel.right - 16, panel.bottom - 24), theme.TEXT_MUTED,
                        anchor="topright")
        else:
            render.text_wrapped(
                surface, self.fonts.tiny(),
                "Rotate the server seed to reveal the one you have been playing on.",
                pygame.Rect(box.x + 30, box.y + 370, box.width - 60, 40),
                theme.TEXT_MUTED,
            )

    def _draw_hash(self, surface: pygame.Surface, value: str, position, width: int) -> None:
        """Hashes are long, so they wrap onto two monospaced lines."""
        font = self.fonts.get(12, mono=True)
        half = len(value) // 2
        for index, chunk in enumerate((value[:half], value[half:])):
            render.text(surface, font, chunk,
                        (position[0], position[1] + index * 15), theme.TEXT)
