from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.enums import AuditAction


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    user_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, name="audit_action"), nullable=False, index=True
    )
    entity_type: Mapped[str | None] = mapped_column(String(60), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    ip_address: Mapped[str | None] = mapped_column(String(60))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)
