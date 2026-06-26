"""Production entry point.

Run with the bundled WSGI server (Waitress, cross-platform):

    python wsgi.py

or via a process manager / container CMD.

Port selection:
  * Uses APP_PORT (default 8000).
  * If that port is already in use, automatically falls back to the next free
    port (APP_PORT+1 … +20, then an OS-assigned one) unless APP_PORT_STRICT=true.
    This keeps `python wsgi.py` working even when 8000 is taken locally.
  * Inside Docker the container's 8000 is always free, so the mapped port is
    stable; change the *host* port via APP_HOST_PORT in docker-compose.
"""
import logging
import os
import socket

from waitress import serve

from app import create_app

log = logging.getLogger("wsgi")

app = create_app()


def _port_is_free(host: str, port: int) -> bool:
    # No SO_REUSEADDR: we want an *exclusive* bind test. On Windows SO_REUSEADDR
    # would let the bind succeed even when the port is in use (false "free").
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _resolve_port(host: str, preferred: int) -> int:
    """Return `preferred` if free; otherwise the next free port, unless strict."""
    if _port_is_free(host, preferred):
        return preferred
    if os.environ.get("APP_PORT_STRICT", "false").strip().lower() in {"1", "true", "yes"}:
        raise SystemExit(
            f"Port {preferred} is already in use and APP_PORT_STRICT is set. "
            f"Free the port or change APP_PORT.")
    for candidate in range(preferred + 1, preferred + 21):
        if _port_is_free(host, candidate):
            log.warning("Port %s busy — falling back to %s.", preferred, candidate)
            return candidate
    # Last resort: let the OS pick any free port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        chosen = sock.getsockname()[1]
    log.warning("Ports %s–%s busy — using OS-assigned port %s.",
                preferred, preferred + 20, chosen)
    return chosen


if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "0.0.0.0")
    preferred = int(os.environ.get("APP_PORT", 8000))
    port = _resolve_port(host, preferred)
    log.info("Serving on http://%s:%s", host, port)
    print(f" * Web app on http://localhost:{port}", flush=True)
    serve(app, host=host, port=port, threads=8)
