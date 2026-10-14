"""
Model ánh xạ bảng 'user_book_interactions'.

Khớp với UserBookInteraction.java — tên cột phải đúng tên cột trong DB.
Các giá trị interaction_type: 'VIEW', 'ADD_TO_CART', 'BUY', 'RATING'
  Trọng số mặc định (khớp InteractionType enum Java):
    VIEW         = 1.0
    ADD_TO_CART  = 3.0
    BUY          = 5.0
    RATING       = số sao thực tế (1-5)
"""
from sqlalchemy import Column, BigInteger, String, Float, Integer, DateTime
from sqlalchemy.sql import func
from app.database import Base


class UserBookInteraction(Base):
    __tablename__ = "user_book_interactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # Lưu id thô (không dùng relationship để tránh N+1 query khi load hàng nghìn bản ghi)
    user_id = Column(BigInteger, name="user_id", nullable=False, index=True)
    book_id = Column(BigInteger, name="book_id", nullable=False, index=True)
    interaction_type = Column(String(30), name="interaction_type", nullable=False)
    weight = Column(Float, nullable=False)
    explicit_rating = Column(Integer, name="explicit_rating", nullable=True)
    created_at = Column(DateTime, name="created_at", server_default=func.now())
