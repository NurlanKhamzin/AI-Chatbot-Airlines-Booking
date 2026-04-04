"""
Start the API + optional Discord bot.

Uses the stdlib asyncio event loop (not uvloop). On macOS, uvicorn's default uvloop
often breaks aiohttp TLS to discord.com — Discord then never logs in.
Run from the project root:  python run.py
"""

from __future__ import annotations

import os

try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        loop="asyncio",
    )
