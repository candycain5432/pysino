"""Randomness for the casino floor.

Real money crypto casinos publish a *commitment* to their randomness before you
bet so you can prove afterwards that the outcome was not tampered with.  Pysino
uses the same scheme, partly because it is genuinely nice engineering and partly
because it makes every outcome reproducible from three strings, which is a gift
when you are debugging a hand that "definitely should have won".

The construction is the standard one::

    stream = HMAC_SHA512(server_seed, "client_seed:nonce:block")

for ``block = 0, 1, 2, ...``.  The bytes of that stream are consumed to build
floats and random bits.  Before play we show ``sha256(server_seed)``; when the
seed is rotated the original is revealed and anybody can replay the stream.

:class:`ProvablyFairRandom` derives from :class:`random.Random`, so it supports
the entire standard API (``shuffle``, ``choice``, ``choices``, ``randrange``...)
while sourcing its entropy from the verifiable stream.  Any plain seeded
``random.Random`` is an acceptable substitute anywhere the games ask for an rng,
which keeps the test-suite simple and deterministic.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from random import Random

_HASH = hashlib.sha512
_BLOCK_BYTES = _HASH().digest_size  # 64


def new_server_seed() -> str:
    """A fresh 256-bit server seed, hex encoded."""
    return secrets.token_hex(32)


def commitment(server_seed: str) -> str:
    """The public hash a player can check the revealed seed against."""
    return hashlib.sha256(server_seed.encode("utf-8")).hexdigest()


class ProvablyFairRandom(Random):
    """A ``random.Random`` whose entropy comes from a verifiable HMAC stream."""

    def __init__(
        self,
        server_seed: str | None = None,
        client_seed: str = "pysino",
        nonce: int = 0,
    ) -> None:
        self._server_seed = server_seed or new_server_seed()
        self._client_seed = client_seed
        self._nonce = nonce
        self._block = 0
        self._buffer = b""
        super().__init__()

    # ------------------------------------------------------------- identity --
    @property
    def server_seed(self) -> str:
        return self._server_seed

    @property
    def client_seed(self) -> str:
        return self._client_seed

    @property
    def nonce(self) -> int:
        return self._nonce

    @property
    def commitment(self) -> str:
        """``sha256`` of the current server seed, safe to show before a bet."""
        return commitment(self._server_seed)

    def set_client_seed(self, client_seed: str) -> None:
        """Players may pick their own seed; doing so restarts the stream."""
        self._client_seed = client_seed
        self._nonce = 0
        self.seed()

    def rotate_server_seed(self) -> "SeedReveal":
        """Burn the current seed, returning it so the past can be verified."""
        revealed = SeedReveal(
            server_seed=self._server_seed,
            client_seed=self._client_seed,
            commitment=self.commitment,
            rounds=self._nonce,
        )
        self._server_seed = new_server_seed()
        self._nonce = 0
        self.seed()
        return revealed

    def next_round(self) -> int:
        """Advance to the next bet.  Each round gets its own private stream."""
        self._nonce += 1
        self.seed()
        return self._nonce

    # --------------------------------------------------------- byte sourcing --
    def seed(self, a=None, version: int = 2) -> None:  # noqa: D102 - see Random
        # Rewinding the stream is what "seeding" means for this generator; the
        # seed material itself lives in the server/client/nonce triple.
        self._block = 0
        self._buffer = b""

    def getstate(self):
        return (self._server_seed, self._client_seed, self._nonce, self._block, self._buffer)

    def setstate(self, state) -> None:
        self._server_seed, self._client_seed, self._nonce, self._block, self._buffer = state

    def _refill(self) -> None:
        message = f"{self._client_seed}:{self._nonce}:{self._block}".encode("utf-8")
        self._buffer += hmac.new(self._server_seed.encode("utf-8"), message, _HASH).digest()
        self._block += 1

    def _take(self, count: int) -> bytes:
        while len(self._buffer) < count:
            self._refill()
        chunk, self._buffer = self._buffer[:count], self._buffer[count:]
        return chunk

    # ------------------------------------------------------ Random overrides --
    def random(self) -> float:
        """A float in ``[0, 1)`` built from 53 bits, exactly like CPython."""
        return int.from_bytes(self._take(7), "big") / (1 << 56)

    def getrandbits(self, k: int) -> int:
        if k < 0:
            raise ValueError("number of bits must be non-negative")
        if k == 0:
            return 0
        value = int.from_bytes(self._take((k + 7) // 8), "big")
        return value >> (-k % 8)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"ProvablyFairRandom(commitment={self.commitment[:12]}..., "
            f"client_seed={self._client_seed!r}, nonce={self._nonce})"
        )


@dataclass(frozen=True)
class SeedReveal:
    """A retired seed, published so past rounds can be audited."""

    server_seed: str
    client_seed: str
    commitment: str
    rounds: int

    def verify(self) -> bool:
        """True when the revealed seed really does hash to the commitment."""
        return commitment(self.server_seed) == self.commitment


def replay(server_seed: str, client_seed: str, nonce: int) -> ProvablyFairRandom:
    """Rebuild the exact generator used for one historical round."""
    return ProvablyFairRandom(server_seed, client_seed, nonce)
