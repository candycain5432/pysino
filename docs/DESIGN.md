# Design notes

Background on the decisions that are not obvious from reading the code.

## Rules engines never import pygame

`pysino/games/` contains plain state machines. `pysino/scenes/` draws them.

The payoff is that the interesting parts — whether a split hand can be a
blackjack, how side pots layer, what a slot payline is worth — are testable
without a display, and can be simulated hundreds of thousands of times in a test
run. It also keeps the scenes honest: a scene that wants to change the rules has
to go and change the rules.

The seam is deliberately narrow. Games never touch the player's chips; they
report what a round costs and what it pays, and the scene moves chips in and out
of the bank. That is why `BlackjackGame.double()` returns the extra stake
instead of deducting it.

## One bank, one save file

There is exactly one `Bank` per session and every game draws from it. That is
the whole premise of the project, so it is a single object rather than a
per-game balance that gets reconciled.

The bank owns persistence too. Saves are written to a temporary file, fsynced,
and moved into place with `os.replace`, so an interrupted save cannot leave a
truncated profile. A profile that fails to parse is replaced with a fresh one
rather than crashing on start-up.

Hold'em is the one game where the player's stack lives somewhere else during a
hand. It syncs on every action: chips leave the bank the moment they are pushed
into the pot, so the top bar never lies.

## The house edge lives in exactly one place per game

This is the rule that caught the only real maths bug in the project. Crash
originally drew its crash point with a `(1 - edge)` numerator *and* had a
separate branch that busted instantly with probability `edge` — subtracting the
edge twice and quietly returning 97% instead of 99%.

The fix was to let the single formula produce the instant busts on its own:
values below 1.00× floor to 1.00×, and that happens with probability exactly
`edge`. Now each game has one place where the house takes its cut:

- **Roulette** — the zero. Every bet covers `n` numbers and pays `36/n - 1`, so
  the 37th pocket *is* the edge. No fudge factor anywhere.
- **Mines** — `(1 - edge) / P(k safe picks)`, which makes every cash-out point
  worth the same.
- **Crash** — `(1 - edge) / (1 - u)`.
- **Blackjack** — emergent from the rules; nothing is scaled.
- **Slots** — emergent from reel weights and the paytable, tuned empirically.

## Tuning the slot machine

The slot is the only game whose numbers cannot be derived in closed form, so it
was tuned against simulation: measure, adjust weights and paytable, measure
again. It sits at roughly 95% RTP, a 48% hit rate and a bonus round about every
120 spins.

Building the reel strips is subtler than it looks. The first version laid each
symbol's copies down in a contiguous block, and because a reel shows three
*consecutive* strip positions at once, every spin showed three of the same
symbol on most reels. The distribution was wildly wrong — 68% RTP with wins
clustered into rare enormous hits.

`build_strip` now spreads each symbol as evenly as its weight allows. A test
asserts no two adjacent positions ever match, because this is exactly the kind
of bug that hides behind a plausible-looking screen.

## Provably fair, for a game with no money in it

Outcomes come from `HMAC_SHA512(server_seed, "client_seed:nonce:block")`, with
`sha256(server_seed)` published before play and the seed revealed on rotation.

There is nothing to cheat at here. It earns its place for two other reasons: any
round can be replayed exactly from three strings, which makes debugging a
specific hand trivial; and `ProvablyFairRandom` subclasses `random.Random`, so
`shuffle`, `sample` and `choice` all work and any seeded `random.Random` can be
dropped in during tests.

## Drawing everything

No image or font files. Cards, chips, slot symbols and the roulette wheel are
built from circles and polygons and cached per size.

Suit pips are vector shapes rather than font glyphs specifically so the cards
look right on a machine with no particular fonts installed — `♠` in a fallback
font is a coin toss. Sound is synthesised as raw 16-bit PCM on first play, and
the whole audio layer degrades to silence if there is no usable device.

The cost is a cache-invalidation wrinkle: `pygame.quit()` kills fonts and
converted surfaces without clearing the flag that says the font module is
running. Each drawing module exposes `clear_cache()` and the app calls them on
start-up, so a second `App` in one process cannot inherit dead handles.

## A fixed canvas

Everything draws onto a fixed 1280×720 surface that is scaled and letterboxed
into the real window, with mouse positions converted back before they reach a
scene. Layout code gets to use absolute coordinates, and the game cannot reflow
or clip at any window size.

Every scene is rendered headless in the test suite, which is how the layout
collisions in the first draft were found — a name plate under a card, a raise
button underneath the bet presets, a roulette ball settling on the wrong number.
None of those would have shown up in a unit test of the rules.
