"""Browser entry point, built with Pygbag: https://pygame-web.github.io/

This file is what ``pygbag`` looks for by default (it wants ``main.py`` at the
project root). It is *not* used for the desktop game - that's ``run.py`` / the
``pysino`` console script, both of which call the plain blocking
:meth:`App.run`. This one calls :meth:`App.run_async` instead, because a
browser tab is single-threaded: a loop that never yields back to the page's
own event loop (paint, input, "page unresponsive" watchdogs) freezes it.

Build and serve locally::

    pip install pygbag
    python -m pygbag .

That opens the built game at http://localhost:8000 in your default browser.
The same command with ``--build`` (no local server) leaves a static
``build/web/`` folder you can deploy anywhere - GitHub Pages, itch.io, or any
plain web host - with no Python involved at that point; everything needed to
run is compiled into the page itself.
"""

from __future__ import annotations

import asyncio

from pysino.app import App


async def main() -> None:
    app = App()
    await app.run_async()


if __name__ == "__main__":
    asyncio.run(main())
