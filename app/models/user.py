"""
Model ánh xạ bảng 'users' phục vụ RecSys xác định danh sách User thật trong hệ thống.
"""
from sqlalchemy import Column, BigInteger, String, Boolean
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True)
    full_name = Column(String(100), name="full_name")
    role = Column(String(20), nullable=False, default="ROLE_CUSTOMER")
    enabled = Column(Boolean, default=True)
