"""
MiroFish-Novel Backend 启动入口
"""

import os
import sys

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config


def main():
    errors = Config.validate()
    if errors:
        print("配置提示:")
        for err in errors:
            print(f"  - {err}")
        print("  - 将继续启动；已具备的离线能力仍可使用。")

    app = create_app()
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 5101))
    debug = Config.DEBUG
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
