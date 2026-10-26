"""
Training Service — lớp trung gian điều phối việc gọi các thuật toán RecSys.
Được gọi bởi API Router, không chứa logic thuật toán.
"""
import logging
from sqlalchemy.orm import Session
from app.algorithms.content_based import run_content_based_training
from app.algorithms.als_recommender import run_collaborative_filtering_training
from app.algorithms.co_purchase import run_co_purchase_training
from app.algorithms.hybrid import run_hybrid_recommendation_training

logger = logging.getLogger(__name__)


class TrainingService:

    @staticmethod
    def train_content_based(db: Session) -> dict:
        """Kích hoạt toàn bộ pipeline Content-Based Filtering."""
        return run_content_based_training(db)

    @staticmethod
    def train_collaborative(db: Session) -> dict:
        """Kích hoạt toàn bộ pipeline Collaborative Filtering ALS."""
        return run_collaborative_filtering_training(db)

    @staticmethod
    def train_co_purchase(db: Session) -> dict:
        """Kích hoạt pipeline Item-Item Co-Purchase (Frequently Bought Together)."""
        return run_co_purchase_training(db)

    @staticmethod
    def train_hybrid(db: Session, alpha: float = None) -> dict:
        """Kích hoạt pipeline Gợi ý Lai ghép (Weighted Hybrid: ALS + Content-Based)."""
        return run_hybrid_recommendation_training(db, alpha=alpha)

    @staticmethod
    def train_all(db: Session) -> dict:
        """
        Kích hoạt tất cả 4 pipeline theo thứ tự:
        1. Content-Based Filtering (nhanh, trích xuất đặc trưng sách & book_similarities)
        2. Item-Item Co-Purchase (tính FBT từ order_items)
        3. Collaborative Filtering ALS (học vector tiềm ẩn người dùng)
        4. Hybrid Recommender (kết hợp tối ưu ALS + CBF ghi vào user_recommendations)
        """
        logger.info("🔄 [TrainingService] Chạy toàn bộ pipeline RecSys (CBF → Co-Purchase → ALS → Hybrid)...")
        cbf_result = run_content_based_training(db)
        co_purchase_result = run_co_purchase_training(db)
        als_result = run_collaborative_filtering_training(db)
        hybrid_result = run_hybrid_recommendation_training(db)
        return {
            "content_based": cbf_result,
            "co_purchase": co_purchase_result,
            "collaborative": als_result,
            "hybrid": hybrid_result,
        }
