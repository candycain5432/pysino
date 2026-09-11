"""Pure rules engines.

Nothing in this package imports pygame.  Every game is a plain state machine
driven by method calls, which keeps the rules testable in isolation and leaves
the scenes in :mod:`pysino.scenes` responsible only for drawing and input.
"""
