"""Shared fixtures.  Every test runs against a throwaway profile directory."""

import random

import pytest


@pytest.fixture(autouse=True)
def isolated_profile(tmp_path, monkeypatch):
    """Keep tests from touching the real save file in ``~/.pysino``."""
    monkeypatch.setenv("PYSINO_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def rng():
    return random.Random(1234)
