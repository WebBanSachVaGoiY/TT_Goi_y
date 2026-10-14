"""
Models ánh xạ 2 bảng kết quả của thuật toán RecSys:
  - BookSimilarity      → bảng 'book_similarities'     (Content-Based Filtering)
  - UserRecommendation  → bảng 'user_recommendations'  (Collaborative Filtering ALS)

LƯU Ý: Cả 2 bảng đều dùng Composite Primary Key (nhiều cột), được khai báo qua PrimaryKeyConstraint.
Điều này khớp với @IdClass trong JPA Entity Java.
"""
from sqlalchemy import Column, BigInteger, String, Float, Integer, DateTime, PrimaryKeyConstraint
from sqlalchemy.sql import func
from app.database import Base


class BookSimilarity(Base):
    """
    Lưu kết quả Content-Based Filtering.
    Composite PK: (book_id_1, book_id_2, similarity_type)
    similarity_type mặc định = 'CONTENT_BASED'
    """
    __tablename__ = "book_similarities"
    __table_args__ = (
        PrimaryKeyConstraint("book_id_1", "book_id_2", "similarity_type"),
    )

    book_id_1 = Column(BigInteger, nullable=False)
    book_id_2 = Column(BigInteger, nullable=False)
    # Khớp với Java: 'CONTENT_BASED', 'ALSO_BOUGHT', 'SAME_AUTHOR'
    similarity_type = Column(String(50), nullable=False)
    score = Column(Float, nullable=False)         # Cosine Similarity [0.0, 1.0]
    rank_order = Column(Integer, nullable=False)  # 1 → top_k
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )


class UserRecommendation(Base):
    """
    Lưu kết quả Collaborative Filtering ALS.
    Composite PK: (user_id, book_id, recommendation_type)
    recommendation_type mặc định = 'FOR_YOU' (khớp RecommendationType.FOR_YOU Java enum)
    """
    __tablename__ = "user_recommendations"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "book_id", "recommendation_type"),
    )

    user_id = Column(BigInteger, nullable=False)
    book_id = Column(BigInteger, nullable=False)
    # Khớp với Java enum RecommendationType: 'FOR_YOU', 'DAILY_DISCOVER'
    recommendation_type = Column(String(30), nullable=False, default="FOR_YOU")
    # Khớp với field algorithm trong UserRecommendation.java: 'ALS', 'CONTENT_BASED', 'HYBRID'
    algorithm = Column(String(50), nullable=True)
    score = Column(Float, nullable=False)         # Điểm dự đoán ALS
    rank_order = Column(Integer, nullable=False)  # 1 → top_k
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )
