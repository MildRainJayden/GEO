from __future__ import annotations

import os

from .api.server import run


if __name__ == "__main__":
    run(port=int(os.environ.get("AIVC_PORT", "8000")))
