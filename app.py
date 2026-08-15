from __future__ import annotations

from app import app, runtime


if __name__ == "__main__":
    app.run(host=runtime.config.app_host, port=runtime.config.app_port)
