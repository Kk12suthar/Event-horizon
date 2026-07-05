from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class Chart(Base):
    __tablename__ = "mt_charts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    type = Column(String(50), nullable=False)
    session_id = Column(String(20), ForeignKey("mt_sessions.id"), nullable=False)

    session = relationship("Session", back_populates="charts")
