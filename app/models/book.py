"""
Models ánh xạ bảng 'books' và 'categories'.

Tên bảng, tên cột phải khớp 100% với các JPA Entity trong book-runner:
  - Book.java       → bảng 'books'
  - Category.java   → bảng 'categories'
"""
from sqlalchemy import Column, BigInteger, String, Text, Numeric, Integer, Float, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    description = Column(Text)


class Book(Base):
    __tablename__ = "books"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    author = Column(String(255))
    publisher = Column(String(255))
    description = Column(Text)
    isbn = Column(String(20), unique=True)
    publication_year = Column(Integer, name="publication_year")
    price = Column(Numeric(12, 2), nullable=False)
    discount_price = Column(Numeric(12, 2), name="discount_price")
    stock_quantity = Column(Integer, name="stock_quantity", default=0)
    page_count = Column(Integer, name="page_count")
    language = Column(String(50))
    cover_image_url = Column(String(500), name="cover_image_url")
    average_rating = Column(Float, name="average_rating", default=0.0)
    total_reviews = Column(Integer, name="total_reviews", default=0)
    sold_count = Column(Integer, name="sold_count", default=0)
    active = Column(Boolean, default=True)
    is_featured = Column(Boolean, name="is_featured", default=False)
    created_at = Column(DateTime, name="created_at", server_default=func.now())
    # FK — chỉ cần lưu id để join, không cần relationship để tránh lazy load
    category_id = Column(BigInteger, name="category_id")
