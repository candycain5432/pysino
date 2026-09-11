"""Entry point: ``python -m pysino``."""

from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    # Printed with flush=True and unbuffered on purpose: on a hosted IDE like
    # Replit, "the app just says Loading and never shows anything" is
    # ambiguous between several very different problems (a slow first-time
    # pip install, no display attached to the container, a stalled
    # pygame.mixer.init()...).  These checkpoints turn that ambiguity into "it
    # got to line X and stopped there", visible in the console the moment it
    # happens rather than only after the process eventually exits.
    print("[pysino] starting up...", flush=True)

    parser = argparse.ArgumentParser(prog="pysino", description="A chip-based casino arcade.")
    parser.add_argument("--scene", default="lobby", help="scene to open on start-up")
    parser.add_argument("--fullscreen", action="store_true", help="start in fullscreen")
    parser.add_argument("--reset", action="store_true", help="wipe the saved profile first")
    args = parser.parse_args(argv)

    from . import config

    if args.reset:
        path = config.save_path()
        if path.exists():
            path.unlink()
            print(f"removed {path}")

    from .app import App

    print("[pysino] opening the display and loading the profile...", flush=True)
    app = App(start_scene=args.scene)
    print("[pysino] window is up, entering the main loop", flush=True)
    if args.fullscreen:
        app.toggle_fullscreen()
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()
    print("[pysino] exited cleanly", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
