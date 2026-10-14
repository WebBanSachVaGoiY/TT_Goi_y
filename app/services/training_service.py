"""
Training Service — lớp trung gian điều phối việc gọi các thuật toán RecSys.
Được gọi bởi API Router, không chứa logic thuật toán.
"""
import logging
from sqlalchemy.orm import Session
from app.algorithms.content_based import run_content_based_training
from app.algorithms.als_recommender import run_collaborative_filtering_training

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
    def train_all(db: Session) -> dict:
        """
        Kích hoạt cả 2 pipeline theo thứ tự:
        1. Content-Based Filtering (nhanh hơn, chạy trước)
        2. Collaborative Filtering ALS (nặng hơn, chạy sau)
        """
        logger.info("🔄 [TrainingService] Chạy toàn bộ pipeline RecSys (CBF → ALS)...")
        cbf_result = run_content_based_training(db)
        als_result = run_collaborative_filtering_training(db)
        return {
            "content_based": cbf_result,
            "collaborative": als_result
        }
