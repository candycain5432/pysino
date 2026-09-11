"""Entry point: ``python -m pysino``."""

from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
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

    app = App(start_scene=args.scene)
    if args.fullscreen:
        app.toggle_fullscreen()
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
