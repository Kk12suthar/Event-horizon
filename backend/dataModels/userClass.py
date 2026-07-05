from sqlalchemy import Column, String, BINARY
from sqlalchemy.orm import relationship
from database import Base
import uuid


class User(Base):
    __tablename__ = "mtd_users"

    id = Column(BINARY(16), primary_key=True, default=lambda: uuid.uuid4().bytes)
    name = Column(String(150), nullable=False)
    email = Column(String(320), nullable=False)
    role = Column(String(20), nullable=False)
    status = Column(String(20), default="active")

    # Relationships
    access_grants = relationship(
        "AccessControl",
        foreign_keys="AccessControl.user_id",
        back_populates="user"
    )
    access_granted = relationship(
        "AccessControl",
        foreign_keys="AccessControl.granted_by",
        back_populates="granted_by_user"
    )
    projects = relationship("Project", back_populates="creator", foreign_keys="Project.created_by")
    folders = relationship("Folder", back_populates="creator", foreign_keys="Folder.created_by")
    dashboards = relationship("Dashboard", back_populates="creator", foreign_keys="Dashboard.created_by")
    files = relationship("File", back_populates="uploader", foreign_keys="File.uploaded_by")
    tables = relationship("Table", back_populates="creator", foreign_keys="Table.created_by")
    sessions = relationship("Session", back_populates="creator", foreign_keys="Session.created_by")
