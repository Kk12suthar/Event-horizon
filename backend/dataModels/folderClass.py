from sqlalchemy import Column, String, DateTime, ForeignKey, BINARY, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone
import uuid


class Folder(Base):
    __tablename__ = "mtd_folder"

    id = Column(BINARY(16), primary_key=True, default=lambda: uuid.uuid4().bytes)
    name = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(BINARY(16), ForeignKey("mtd_users.id"), nullable=False)
    status = Column(String(20), nullable=False)
    project_id = Column(BINARY(16), ForeignKey("mtd_project.id"), nullable=False)

    # Relationships
    project = relationship("Project", back_populates="folders")
    creator = relationship("User", foreign_keys=[created_by], back_populates="folders")
    dashboards = relationship("Dashboard", back_populates="parent_folder")
    files = relationship("File", back_populates="parent_folder")
    sessions = relationship("Session", back_populates="folder")
