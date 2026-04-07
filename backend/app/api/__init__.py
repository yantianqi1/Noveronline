"""
API 蓝图
"""

from flask import Blueprint

project_bp = Blueprint("project", __name__)
novel_bp = Blueprint("novel", __name__)
worldline_bp = Blueprint("worldline", __name__)
llm_bp = Blueprint("llm", __name__)
archive_bp = Blueprint("archive", __name__)
assets_bp = Blueprint("assets", __name__)

from . import project  # noqa: E402,F401
from . import project_graph  # noqa: E402,F401
from . import novel  # noqa: E402,F401
from . import llm  # noqa: E402,F401
from . import archive  # noqa: E402,F401
from . import assets  # noqa: E402,F401
from . import worldline_support  # noqa: E402,F401
from . import worldline_session  # noqa: E402,F401
from . import worldline_interaction  # noqa: E402,F401
from . import worldline_prepare  # noqa: E402,F401
from . import worldline_auto_evolution  # noqa: E402,F401
from . import worldline_events  # noqa: E402,F401
from . import worldline_auto_evolution_sse  # noqa: E402,F401
from .writer_agent import writer_agent_bp  # noqa: E402,F401
