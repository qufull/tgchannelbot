from sqlalchemy.orm import   Mapped, mapped_column, relationship
from sqlalchemy import String, Text, Integer, BigInteger, DateTime,  func, UniqueConstraint

from src.utils.db import Base


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    source_chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    source_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    original_text: Mapped[str] = mapped_column(Text, default="")
    rewritten_text: Mapped[str] = mapped_column(Text, default="")

    notified: Mapped[int] = mapped_column(Integer, default=0)  # 0/1

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    media_items: Mapped[list["MediaItem"]] = relationship(
        back_populates="post", cascade="all, delete-orphan", order_by="MediaItem.sort_index"
    )

    __table_args__ = (
        UniqueConstraint("source_chat_id", "media_group_id", name="uq_post_group", sqlite_on_conflict="IGNORE"),
    )
