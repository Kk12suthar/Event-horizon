from sqlalchemy import Column, String, DateTime, ForeignKey, BINARY
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone
import uuid


class File(Base):
    __tablename__ = "mtd_file"

    id = Column(BINARY(16), primary_key=True, default=lambda: uuid.uuid4().bytes)
    name = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    uploaded_by = Column(BINARY(16), ForeignKey("mtd_users.id"), nullable=False)
    status = Column(String(20), nullable=False)
    parent_folder_id = Column(BINARY(16), ForeignKey("mtd_folder.id"), nullable=False)
    original_name = Column(String(100), nullable=True)

    # Relationships
    parent_folder = relationship("Folder", back_populates="files")
    uploader = relationship("User", foreign_keys=[uploaded_by], back_populates="files")
    tables = relationship("Table", back_populates="file")
