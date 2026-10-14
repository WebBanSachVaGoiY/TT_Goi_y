"""
REST API Router cho RecSys Microservice.
Tất cả endpoint đều có prefix /api/recsys.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.services.training_service import TrainingService
from app.config import get_settings

router = APIRouter(prefix="/api/recsys", tags=["RecSys Training"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get(
    "/health",
    summary="Kiểm tra trạng thái service và kết nối DB"
)
def health_check(db: Session = Depends(get_db)):
    """
    Trả về trạng thái hoạt động của RecSys Service và kết nối MariaDB.
    Dùng để xác nhận service đã sẵn sàng trước khi trigger training.
    """
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "service": "BookRunner RecSys Microservice",
        "version": "1.0.0",
        "status": "running",
        "database": {
            "status": db_status,
            "name": settings.DB_NAME,
            "host": settings.DB_HOST,
        },
        "config": {
            "cbf_top_k": settings.CBF_TOP_K,
            "als_factors": settings.ALS_FACTORS,
            "als_iterations": settings.ALS_ITERATIONS,
            "als_alpha": settings.ALS_ALPHA,
            "time_decay_lambda": settings.TIME_DECAY_LAMBDA,
        }
    }


@router.post(
    "/train/content-based",
    status_code=status.HTTP_200_OK,
    summary="Kích hoạt huấn luyện Content-Based Filtering",
    description=(
        "Tính TF-IDF & Cosine Similarity cho toàn bộ sách active, "
        "sau đó ghi Top-10 sách tương tự nhất vào bảng book_similarities "
        "với similarity_type='CONTENT_BASED'."
    )
)
def train_content_based(db: Session = Depends(get_db)):
    try:
        result = TrainingService.train_content_based(db)
        return {
            "message": "Content-Based Filtering training hoàn thành!",
            "result": result
        }
    except Exception as e:
        logger.error(f"❌ [CBF] Lỗi: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi Content-Based training: {str(e)}"
        )


@router.post(
    "/train/collaborative",
    status_code=status.HTTP_200_OK,
    summary="Kích hoạt huấn luyện Collaborative Filtering ALS",
    description=(
        "Huấn luyện mô hình ALS với Implicit Feedback + Time-Decay từ bảng "
        "user_book_interactions, sau đó ghi Top-20 sách gợi ý cá nhân hóa "
        "vào bảng user_recommendations với recommendation_type='FOR_YOU'."
    )
)
def train_collaborative(db: Session = Depends(get_db)):
    try:
        result = TrainingService.train_collaborative(db)
        return {
            "message": "Collaborative Filtering ALS training hoàn thành!",
            "result": result
        }
    except Exception as e:
        logger.error(f"❌ [ALS] Lỗi: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi ALS training: {str(e)}"
        )


@router.post(
    "/train/all",
    status_code=status.HTTP_200_OK,
    summary="Kích hoạt toàn bộ pipeline RecSys (CBF → ALS)",
    description="Chạy tuần tự Content-Based Filtering rồi đến Collaborative Filtering ALS."
)
def train_all(db: Session = Depends(get_db)):
    try:
        result = TrainingService.train_all(db)
        return {
            "message": "Toàn bộ pipeline RecSys hoàn thành!",
            "result": result
        }
    except Exception as e:
        logger.error(f"❌ [train_all] Lỗi: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
