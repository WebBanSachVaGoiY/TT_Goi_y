from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,    # Kiểm tra connection còn sống trước khi dùng (tránh "MySQL server has gone away")
    pool_recycle=3600,     # Tái tạo connection sau 1 giờ
    pool_size=5,
    max_overflow=10,
    echo=False             # Đổi thành True để xem SQL log khi debug
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency injection session cho FastAPI route handlers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
