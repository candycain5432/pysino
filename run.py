#!/usr/bin/env python3
"""Convenience launcher so the game runs with a plain ``python run.py``."""

import sys

from pysino.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
