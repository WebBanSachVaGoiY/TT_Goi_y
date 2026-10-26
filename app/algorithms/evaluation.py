"""
Module đo lường và đánh giá chất lượng mô hình gợi ý RecSys (Evaluation Metrics).
Hiện thực hóa Mục 11 trong RECSYS_DOCUMENTATION.md.

Chỉ số đo lường:
  1. Precision@K (K=10): Tỷ lệ sách gợi ý mà người dùng thực sự quan tâm trong tập Test.
  2. Recall@K (K=10): Tỷ lệ sách người dùng thích được hệ thống tìm ra thành công.
  3. NDCG@K (Normalized Discounted Cumulative Gain): Đánh giá chất lượng thứ tự xếp hạng.
  4. Catalog Coverage (%): Độ phủ của toàn bộ danh mục sách trong kết quả gợi ý.
"""
import math
import logging
from collections import defaultdict
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.book import Book
from app.models.interaction import UserBookInteraction
from app.models.recommendation import UserRecommendation
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def compute_ndcg_at_k(actual_items: set, recommended_items: list, k: int) -> float:
    r"""
    Tính Normalized Discounted Cumulative Gain tại Top-K.
    DCG@K = \sum_{i=1}^K \frac{rel_i}{\log_2(i + 1)}
    với rel_i = 1 nếu item ở vị trí i thuộc actual_items, ngược lại = 0.
    """
    dcg = 0.0
    for i, item in enumerate(recommended_items[:k]):
        if item in actual_items:
            dcg += 1.0 / math.log2(i + 2)  # i là 0-indexed, vị trí 1 là log2(2) = 1

    ideal_hits = min(len(actual_items), k)
    if ideal_hits == 0:
        return 0.0

    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_recommendations(db: Session, top_k: int = 10) -> dict:
    """
    Đánh giá mô hình Collaborative Filtering dựa trên ground truth từ bảng user_book_interactions
    và kết quả gợi ý trong bảng user_recommendations (recommendation_type='FOR_YOU').

    Chiến lược Hold-out:
      - Với mỗi user, các tương tác gần nhất (20% cuối) hoặc các tương tác có giá trị cao
        (BUY, ADD_TO_CART, hoặc RATING >= 4) được dùng làm tập Test (Ground Truth).
      - So sánh với Top-K sách trong bảng user_recommendations.
    """
    logger.info(f"📊 [Evaluation] Bắt đầu đánh giá mô hình RecSys tại Top-{top_k}...")

    # 1. Tính Catalog Coverage
    total_active_books = db.query(Book.id).filter(Book.active == True).count()
    distinct_rec_books = (
        db.query(UserRecommendation.book_id)
        .filter(UserRecommendation.recommendation_type == settings.RECOMMENDATION_TYPE)
        .distinct()
        .all()
    )
    rec_book_ids = set(r[0] for r in distinct_rec_books)

    coverage_pct = 0.0
    if total_active_books > 0:
        coverage_pct = round((len(rec_book_ids) / total_active_books) * 100.0, 2)

    # 2. Đọc tất cả gợi ý của từng user (FOR_YOU)
    recs_by_user = defaultdict(list)
    user_recs = (
        db.query(UserRecommendation.user_id, UserRecommendation.book_id, UserRecommendation.rank_order)
        .filter(UserRecommendation.recommendation_type == settings.RECOMMENDATION_TYPE)
        .order_by(UserRecommendation.user_id, UserRecommendation.rank_order.asc())
        .all()
    )
    for uid, bid, _rank in user_recs:
        recs_by_user[uid].append(bid)

    if not recs_by_user:
        return {
            "status": "warning",
            "message": "Bảng user_recommendations trống. Vui lòng chạy huấn luyện ALS trước khi đánh giá.",
            "metrics": {
                "precision_at_k": 0.0,
                "recall_at_k": 0.0,
                "ndcg_at_k": 0.0,
                "catalog_coverage_pct": coverage_pct,
                "total_active_books": total_active_books,
                "distinct_recommended_books": len(rec_book_ids),
                "evaluated_users": 0,
                "top_k": top_k,
            }
        }

    # 3. Gom tương tác của user để tạo Ground Truth
    interactions = (
        db.query(
            UserBookInteraction.user_id,
            UserBookInteraction.book_id,
            UserBookInteraction.interaction_type,
            UserBookInteraction.weight,
            UserBookInteraction.created_at
        )
        .order_by(UserBookInteraction.user_id, UserBookInteraction.created_at.asc())
        .all()
    )

    user_interactions = defaultdict(list)
    for row in interactions:
        user_interactions[row.user_id].append(row)

    precisions = []
    recalls = []
    ndcgs = []
    evaluated_users_count = 0

    for user_id, rec_books in recs_by_user.items():
        user_history = user_interactions.get(user_id, [])
        if len(user_history) < 3:
            continue  # Bỏ qua user có quá ít dữ liệu kiểm thử

        # Lấy 25% tương tác gần nhất làm Test Set (hoặc tương tác mua/giỏ hàng)
        split_idx = max(1, int(len(user_history) * 0.75))
        test_history = user_history[split_idx:]

        # Ground truth: các sách trong test set mà user đã tương tác tích cực
        # (hoặc bất kỳ sách nào trong test set)
        test_book_ids = set(item.book_id for item in test_history)
        if not test_book_ids:
            continue

        top_k_recs = rec_books[:top_k]
        hits = len(set(top_k_recs) & test_book_ids)

        prec = hits / float(top_k)
        rec = hits / float(len(test_book_ids))
        ndcg_val = compute_ndcg_at_k(test_book_ids, top_k_recs, top_k)

        precisions.append(prec)
        recalls.append(rec)
        ndcgs.append(ndcg_val)
        evaluated_users_count += 1

    avg_precision = round(sum(precisions) / len(precisions), 4) if precisions else 0.0
    avg_recall = round(sum(recalls) / len(recalls), 4) if recalls else 0.0
    avg_ndcg = round(sum(ndcgs) / len(ndcgs), 4) if ndcgs else 0.0

    result = {
        "status": "success",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            f"precision_at_{top_k}": avg_precision,
            f"recall_at_{top_k}": avg_recall,
            f"ndcg_at_{top_k}": avg_ndcg,
            "catalog_coverage_pct": coverage_pct,
            "total_active_books": total_active_books,
            "distinct_recommended_books": len(rec_book_ids),
            "evaluated_users": evaluated_users_count,
            "top_k": top_k,
        },
        "summary": (
            f"Mô hình đạt Precision@{top_k} = {avg_precision*100:.2f}%, "
            f"Recall@{top_k} = {avg_recall*100:.2f}%, NDCG@{top_k} = {avg_ndcg:.4f}, "
            f"Độ phủ danh mục: {coverage_pct}% ({len(rec_book_ids)}/{total_active_books} sách)."
        )
    }

    logger.info(f"✅ [Evaluation] Hoàn thành đánh giá: {result['summary']}")
    return result
