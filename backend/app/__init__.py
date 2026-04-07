"""
MiroFish-Novel Flask 应用工厂
"""

from flask import Flask
from flask_cors import CORS

from .config import Config
from .services.archive_library_storage import ArchiveLibraryStorage
from .services.llm_storage import LlmStorage
from .utils.logger import setup_logger


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
        app.json.ensure_ascii = False

    setup_logger("mirofish_novel")
    LlmStorage()
    ArchiveLibraryStorage()
    CORS(
        app,
        resources={r"/api/*": {"origins": "*"}},
        allow_private_network=True,
    )

    from .api import (
        archive_bp, assets_bp, llm_bp, novel_bp, project_bp,
        unified_assets_bp, worldline_bp, writer_agent_bp,
    )

    app.register_blueprint(project_bp, url_prefix="/api/project")
    app.register_blueprint(novel_bp, url_prefix="/api/novel")
    app.register_blueprint(worldline_bp, url_prefix="/api/worldline")
    app.register_blueprint(llm_bp, url_prefix="/api/llm")
    app.register_blueprint(archive_bp, url_prefix="/api/archive")
    app.register_blueprint(assets_bp, url_prefix="/api/assets")
    app.register_blueprint(unified_assets_bp, url_prefix="/api/unified-assets")
    app.register_blueprint(writer_agent_bp, url_prefix="/api/writer-agent")

    @app.route("/health")
    def health():
        return {"status": "ok", "service": "MiroFish-Novel Backend"}

    return app
