"""MiroFish-Novel FastAPI backend entrypoint."""

import os
import sys

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import Config


def main():
    errors = Config.validate()
    if errors:
        print("配置提示:")
        for err in errors:
            print(f"  - {err}")
        print("  - 将继续启动；已具备的离线能力仍可使用。")

    host = os.environ.get("APP_HOST", "0.0.0.0")
    port = int(os.environ.get("APP_PORT", 3888))

    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=Config.DEBUG)


if __name__ == "__main__":
    main()
