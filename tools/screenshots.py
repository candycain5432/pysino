#!/usr/bin/env python3
"""Render every scene headless and save a PNG of each.

Doubles as a smoke test: it drives real interactions (dealing, spinning,
betting) so a crash in any scene shows up here rather than in front of a
player.  Run with ``python tools/screenshots.py [outdir]``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame  # noqa: E402

from pysino.app import App  # noqa: E402


def advance(app: App, frames: int = 1, dt: float = 1 / 60) -> None:
    for _ in range(frames):
        app.step(dt)


def click(app: App, position, button: int = 1) -> None:
    """Synthesise a click in canvas coordinates."""
    scene = app.scenes.current
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        scene.handle_event(pygame.event.Event(kind, {"pos": position, "button": button}))


def press(app: App, key: int) -> None:
    app.scenes.current.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": key, "unicode": "", "mod": 0})
    )


def save(app: App, out: Path, name: str) -> None:
    pygame.image.save(app.canvas, str(out / f"{name}.png"))
    print(f"  wrote {name}.png")


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
    out.mkdir(parents=True, exist_ok=True)

    app = App(headless=True)
    app.bank.chips = 25_000
    app.chip_ticker.set(25_000, immediate=True)

    print("lobby")
    app.go_to("lobby", instant=True)
    advance(app, 30)
    save(app, out, "01-lobby")

    print("blackjack")
    app.go_to("blackjack", instant=True)
    advance(app, 5)
    press(app, pygame.K_SPACE)          # deal
    advance(app, 60)
    save(app, out, "02-blackjack")

    print("holdem")
    app.go_to("holdem", instant=True)
    advance(app, 240)                   # let the bots act
    save(app, out, "03-holdem")

    print("slots")
    app.go_to("slots", instant=True)
    advance(app, 5)
    press(app, pygame.K_SPACE)
    advance(app, 150)
    save(app, out, "04-slots")

    print("roulette")
    app.go_to("roulette", instant=True)
    advance(app, 5)
    scene = app.scenes.current
    for key in ("straight-17", "red", "dozen-1", "corner-1", "split-5-8"):
        click(app, scene._spot_by_key[key].rect.center)
    advance(app, 10)
    save(app, out, "05-roulette-bets")
    press(app, pygame.K_SPACE)
    advance(app, 260)
    save(app, out, "06-roulette-spun")

    print("mines")
    app.go_to("mines", instant=True)
    advance(app, 5)
    press(app, pygame.K_SPACE)
    advance(app, 10)
    scene = app.scenes.current
    for position in (0, 6, 12, 18):
        if scene.game.state.value == "playing":
            click(app, scene._tile_rect(position).center)
            advance(app, 8)
    advance(app, 20)
    save(app, out, "07-mines")

    print("crash")
    app.go_to("crash", instant=True)
    advance(app, 5)
    press(app, pygame.K_SPACE)
    advance(app, 70)
    save(app, out, "08-crash")

    print("video poker")
    app.go_to("videopoker", instant=True)
    advance(app, 5)
    press(app, pygame.K_SPACE)          # deal
    advance(app, 40)
    press(app, pygame.K_1)
    press(app, pygame.K_2)
    advance(app, 10)
    save(app, out, "09-videopoker")

    print("stats")
    app.go_to("stats", instant=True)
    advance(app, 10)
    save(app, out, "10-stats")

    print("settings")
    app.go_to("settings", instant=True)
    advance(app, 10)
    app.scenes.current._rotate()
    advance(app, 10)
    save(app, out, "11-settings")

    print(f"\nall scenes rendered into {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
