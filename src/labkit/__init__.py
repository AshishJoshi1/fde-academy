"""labkit runs *inside* each lesson subprocess (Milestone 1 steps 2 and 6b).

It will provide: the IPC client back to the server, log/print/input() capture,
call-site and locals snapshots via sys._current_frames(), the sys.monitoring
line gutter, and optional checkpoint()/show(). Standard library only.
"""
__version__ = "0.1.0"
