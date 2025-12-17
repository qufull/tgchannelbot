
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from src.utils.db import Base


class AISettings(Base):
    __tablename__ = "ai_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())