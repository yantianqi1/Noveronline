"""Small helpers for concise SQLAlchemy Core table definitions."""

from sqlalchemy import Column, Float, Integer, PrimaryKeyConstraint, String, Table

from .base import metadata


def text_col(name: str, *, nullable: bool = True, primary_key: bool = False, default: str | None = None):
    return Column(name, String, nullable=nullable, primary_key=primary_key, server_default=default)


def int_col(name: str, *, nullable: bool = True, default: str | None = None):
    return Column(name, Integer, nullable=nullable, server_default=default)


def float_col(name: str, *, nullable: bool = True, default: str | None = None):
    return Column(name, Float, nullable=nullable, server_default=default)


def project_id(nullable: bool = False):
    return text_col("project_id", nullable=nullable)


def table(name: str, *items):
    return Table(name, metadata, *items, extend_existing=True)


def composite_pk(*columns: str):
    return PrimaryKeyConstraint(*columns)
