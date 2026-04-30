"""
ASTRA — Per-project ID sequence (F-074)
=========================================
File: backend/app/models/id_sequence.py

Replaces the racy ``count + 1`` and ``ORDER BY id DESC … parse trailing
digits`` patterns scattered across `routers/interface.py`,
`routers/interface_import.py`, and `routers/projects.py`. Each pattern
read the table, computed an ID locally, and inserted — two concurrent
creates on the same project could (and on Postgres did) compute the
same ID.

This table holds one row per (project_id, prefix). The
``next_human_id`` helper SELECTs the row FOR UPDATE, increments
``next_value``, and returns the formatted ID inside the same
transaction. Callers must not commit between the helper call and
the INSERT they're sequencing.
"""

from __future__ import annotations

from sqlalchemy import (
    Column, Integer, String, ForeignKey, PrimaryKeyConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class IdSequence(Base):
    __tablename__ = "id_sequences"

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    prefix = Column(String(64), nullable=False)
    next_value = Column(Integer, nullable=False, default=1)

    project = relationship("Project")

    __table_args__ = (
        PrimaryKeyConstraint("project_id", "prefix", name="pk_id_sequences"),
    )
