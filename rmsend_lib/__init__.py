"""rmsend library: article extraction, e-ink rendering and reMarkable transports.

The `rmsend` shim adds this directory's parent to sys.path so the whole tool still runs as a
single `uv run --script`. Only `article` needs third-party packages (requests, trafilatura,
lxml); `render` and `device` are standard-library only so their tests run anywhere.
"""
