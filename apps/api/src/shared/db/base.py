from sqlalchemy import MetaData


metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

# Import table definitions so metadata is populated from a single entrypoint.
from src.shared.db import archive_library  # noqa: E402,F401
from src.shared.db import graph  # noqa: E402,F401
from src.shared.db import llm_facility  # noqa: E402,F401
from src.shared.db import shared_kernel  # noqa: E402,F401
from src.shared.db import worldline  # noqa: E402,F401
from src.shared.db import writer  # noqa: E402,F401
