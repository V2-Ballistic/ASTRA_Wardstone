"""
ASTRA — Generic Document model
==================================
File: backend/app/models/document.py   ← NEW (parts module)

Minimal document store for non-supplier-bound files (STEP CAD uploads,
assembly STEP files, etc.). Distinct from `SupplierDocument` which is
required to belong to a `Supplier`. STEP files for the parts library
do not always come from a supplier.
"""

from sqlalchemy import (
    Column, Integer, String, BigInteger, DateTime, ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id              = Column(Integer, primary_key=True, index=True)
    filename        = Column(String(500), nullable=False)
    file_path       = Column(String(1000), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    sha256          = Column(String(64), nullable=False, index=True)
    mime_type       = Column(String(100), nullable=False)
    document_type   = Column(String(100), nullable=True)
    uploaded_by_id  = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at     = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    uploaded_by     = relationship("User", foreign_keys=[uploaded_by_id])
