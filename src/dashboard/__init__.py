"""Decision dashboard for the Upworthy Research Archive.

A thin FastAPI JSON API (server.py) over abkit + the precomputed batch
results, plus a hand-built static single-page frontend in web/. Read-only:
nothing here fits, tunes, or persists anything, and every statistic is
computed by abkit — the frontend renders numbers, it never derives them.
"""
