from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, BINARY
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone
import uuid


class Dashboard(Base):
    __tablename__ = "mtd_dashboard"

    id = Column(BINARY(16), primary_key=True, default=lambda: uuid.uuid4().bytes)
    name = Column(String(50), nullable=False)
    description = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(BINARY(16), ForeignKey("mtd_users.id"), nullable=False)
    status = Column(String(20), nullable=False)
    parent_folder_id = Column(BINARY(16), ForeignKey("mtd_folder.id"), nullable=False)
    layout_config = Column(JSON, nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], back_populates="dashboards")
    parent_folder = relationship("Folder", back_populates="dashboards")
