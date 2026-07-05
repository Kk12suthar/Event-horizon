from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, BINARY
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone
import uuid


class Session(Base):
    __tablename__ = "mtd_session"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(BINARY(16), ForeignKey("mtd_users.id"), nullable=False)
    status = Column(String(20), nullable=False)
    folder_id = Column(BINARY(16), ForeignKey("mtd_folder.id"), nullable=False)
    app_name = Column(String(45), nullable=False)
    entities = Column(JSON, nullable=True)

    # Relationships
    folder = relationship("Folder", back_populates="sessions")
    creator = relationship("User", foreign_keys=[created_by], back_populates="sessions")
    results = relationship("Result", back_populates="session")
