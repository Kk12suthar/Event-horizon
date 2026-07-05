from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, BINARY
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone


class AccessControl(Base):
    __tablename__ = "mtd_access"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(BINARY(16), nullable=False)
    entity_type = Column(String(20), nullable=False)
    user_id = Column(BINARY(16), ForeignKey("mtd_users.id"), nullable=False)
    level = Column(String(20), nullable=False)
    granted_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    granted_by = Column(BINARY(16), ForeignKey("mtd_users.id"), nullable=False)
    expiration_date = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="access_grants")
    granted_by_user = relationship("User", foreign_keys=[granted_by], back_populates="access_granted")
