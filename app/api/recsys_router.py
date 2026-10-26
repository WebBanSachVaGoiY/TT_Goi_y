"""
REST API Router cho RecSys Microservice.
Tất cả endpoint đều có prefix /api/recsys.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.services.training_service import TrainingService
from app.config import get_settings
from app.models.book import Book
from app.models.recommendation import BookSimilarity, UserRecommendation

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
    "/train/co-purchase",
    status_code=status.HTTP_200_OK,
    summary="Kích hoạt huấn luyện Item-Item Co-Purchase (Frequently Bought Together)",
    description=(
        "Đọc các đơn hàng hợp lệ từ order_items (loại CANCELLED/RETURNED), "
        "đếm các cặp sách cùng xuất hiện trong một đơn, chuẩn hoá Cosine rồi "
        "ghi Top-10 sách 'thường được mua cùng' vào book_similarities "
        "với similarity_type='ALSO_BOUGHT'."
    )
)
def train_co_purchase(db: Session = Depends(get_db)):
    try:
        result = TrainingService.train_co_purchase(db)
        return {
            "message": "Item-Item Co-Purchase training hoàn thành!",
            "result": result
        }
    except Exception as e:
        logger.error(f"❌ [CoPurchase] Lỗi: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi Co-Purchase training: {str(e)}"
        )


@router.post(
    "/train/hybrid",
    status_code=status.HTTP_200_OK,
    summary="Kích hoạt huấn luyện Gợi ý Lai ghép (Hybrid Recommender: ALS + Content-Based)",
    description=(
        "Kết hợp ưu điểm của Collaborative Filtering (ALS) và Content-Based (TF-IDF), "
        "áp dụng Dynamic Item Confidence Weighting để giải quyết bài toán Item Cold-Start, "
        "ghi Top-20 sách gợi ý cá nhân hoá tối ưu vào bảng user_recommendations với recommendation_type='FOR_YOU'."
    )
)
def train_hybrid(
    alpha: float = Query(None, ge=0.0, le=1.0, description="Trọng số ALS (mặc định 0.65, 1-alpha là CBF)"),
    db: Session = Depends(get_db)
):
    try:
        result = TrainingService.train_hybrid(db, alpha=alpha)
        return {
            "message": "Gợi ý Lai ghép (Hybrid Recommender) hoàn thành!",
            "result": result
        }
    except Exception as e:
        logger.error(f"❌ [Hybrid] Lỗi: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi Hybrid training: {str(e)}"
        )


@router.post(
    "/train/all",
    status_code=status.HTTP_200_OK,
    summary="Kích hoạt toàn bộ pipeline RecSys (CBF → Co-Purchase → ALS → Hybrid)",
    description="Chạy tuần tự Content-Based Filtering, Item-Item Co-Purchase, Collaborative Filtering ALS rồi Hybrid Recommender."
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


# =====================================================================
# READ ENDPOINTS — dùng cho debug/Swagger/SDK; Spring Boot là cổng chính
# cho Frontend (đọc trực tiếp DB). Các endpoint này đọc lại kết quả đã train.
# =====================================================================

@router.get(
    "/users/{user_id}/recommendations",
    summary="Đọc gợi ý cá nhân hoá (FOR_YOU) của một user",
    description="Trả về danh sách sách gợi ý đã train trong bảng user_recommendations, sắp theo rank_order.",
)
def get_user_recommendations(
    user_id: int,
    limit: int = Query(20, ge=1, le=100, description="Số gợi ý tối đa"),
    recommendation_type: str = Query(settings.RECOMMENDATION_TYPE, description="Loại gợi ý (mặc định FOR_YOU)"),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(UserRecommendation)
        .filter(
            UserRecommendation.user_id == user_id,
            UserRecommendation.recommendation_type == recommendation_type,
        )
        .order_by(UserRecommendation.rank_order.asc())
        .limit(limit)
        .all()
    )
    items = [
        {
            "book_id": r.book_id,
            "score": float(r.score),
            "rank_order": r.rank_order,
            "algorithm": r.algorithm,
        }
        for r in rows
    ]
    return {
        "user_id": user_id,
        "recommendation_type": recommendation_type,
        "count": len(items),
        "items": items,
    }


def _get_book_similarity(
    db: Session,
    book_id: int,
    similarity_type: str,
    limit: int,
):
    rows = (
        db.query(BookSimilarity)
        .filter(
            BookSimilarity.book_id_1 == book_id,
            BookSimilarity.similarity_type == similarity_type,
        )
        .order_by(BookSimilarity.rank_order.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "book_id": r.book_id_2,
            "score": float(r.score),
            "rank_order": r.rank_order,
        }
        for r in rows
    ]


@router.get(
    "/books/{book_id}/similar",
    summary="Đọc sách tương tự (Content-Based) của một sách",
    description="Trả về Top-K sách tương tự theo nội dung từ bảng book_similarities (similarity_type='CONTENT_BASED').",
)
def get_similar_books(
    book_id: int,
    limit: int = Query(10, ge=1, le=100, description="Số sách tương tự tối đa"),
    db: Session = Depends(get_db),
):
    items = _get_book_similarity(db, book_id, settings.CBF_SIMILARITY_TYPE, limit)
    return {"book_id": book_id, "similarity_type": settings.CBF_SIMILARITY_TYPE, "count": len(items), "items": items}


@router.get(
    "/books/{book_id}/frequently-bought-together",
    summary="Đọc sách 'thường được mua cùng' (Co-Purchase)",
    description="Trả về Top-K sách thường được mua cùng từ bảng book_similarities (similarity_type='ALSO_BOUGHT').",
)
def get_frequently_bought_together(
    book_id: int,
    limit: int = Query(10, ge=1, le=100, description="Số sách tối đa"),
    db: Session = Depends(get_db),
):
    items = _get_book_similarity(db, book_id, settings.CO_PURCHASE_SIMILARITY_TYPE, limit)
    return {
        "book_id": book_id,
        "similarity_type": settings.CO_PURCHASE_SIMILARITY_TYPE,
        "count": len(items),
        "items": items,
    }


@router.get(
    "/trending",
    summary="Đọc danh sách sách bán chạy (fallback cold-start)",
    description="Trả về Top-K sách active theo sold_count giảm dần, ưu tiên average_rating khi đồng hạng.",
)
def get_trending(
    limit: int = Query(20, ge=1, le=100, description="Số sách tối đa"),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Book)
        .filter(Book.active == True)
        .order_by(Book.sold_count.desc(), Book.average_rating.desc())
        .limit(limit)
        .all()
    )
    items = [
        {
            "book_id": b.id,
            "title": b.title,
            "sold_count": b.sold_count,
            "average_rating": float(b.average_rating) if b.average_rating is not None else 0.0,
            "rank_order": idx + 1,
        }
        for idx, b in enumerate(rows)
    ]
    return {"count": len(items), "items": items}


@router.get(
    "/evaluate",
    summary="Đo lường & đánh giá chất lượng mô hình RecSys",
    description="Tính toán các chỉ số Precision@K, Recall@K, NDCG@K và Catalog Coverage (Mục 11 RecSys Spec).",
)
def evaluate_model(
    top_k: int = Query(10, ge=1, le=50, description="K chỉ số đánh giá (mặc định 10)"),
    db: Session = Depends(get_db),
):
    try:
        from app.algorithms.evaluation import evaluate_recommendations
        return evaluate_recommendations(db, top_k=top_k)
    except Exception as e:
        logger.error(f"❌ [evaluate] Lỗi: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi đánh giá mô hình: {str(e)}"
        )
