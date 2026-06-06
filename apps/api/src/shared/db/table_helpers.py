from sqlalchemy import Column, DateTime


def timestamp_columns() -> tuple[Column, Column]:
    return (
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
