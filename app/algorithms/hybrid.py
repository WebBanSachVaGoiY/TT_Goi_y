"""
Thuật toán Gợi ý Lai ghép (Weighted Hybrid Recommender System) cho BookRunner.

Kết hợp 2 mô hình:
    1. Collaborative Filtering ALS (Implicit Feedback + Time-Decay)
    2. Content-Based Filtering (TF-IDF + Cosine Similarity)

Công thức kết hợp có trọng số động giải quyết triệt để Item Cold-Start:
    Score_Hybrid(u, i) = α_i * Norm(Score_ALS(u, i)) + (1 - α_i) * Score_CBF(u, i)

Trong đó:
    - Norm(Score_ALS) là Min-Max scaling về thang đo [0, 1].
    - Score_CBF(u, i) là Cosine Similarity giữa Vector sở thích của User (tổng hợp từ sách đã tương tác)
      và Vector đặc trưng TF-IDF của sách i.
    - Trọng số động α_i = α * min(1.0, count_interactions(i) / item_cold_start_threshold).
      Khi sách mới lên sàn chưa có tương tác (Item Cold-Start), α_i = 0, hệ thống tự động
      gợi ý sách dựa 100% vào nội dung tương đồng với sở thích của người dùng.
      Khi sách đã tích lũy tương tác, α_i đạt ngưỡng chuẩn (mặc định α = 0.65).

Kết quả: ghi đè vào bảng user_recommendations với recommendation_type='FOR_YOU', algorithm='HYBRID'
để Spring Boot phục vụ người dùng qua endpoint GET /api/v1/recommendations/for-you.
"""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
import logging
from datetime import datetime, timezone
import numpy as np
import scipy.sparse as sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from implicit.als import AlternatingLeastSquares
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.book import Book, Category
from app.models.interaction import UserBookInteraction
from app.models.recommendation import UserRecommendation
from app.models.user import User
from app.config import get_settings
from app.algorithms.content_based import _build_book_document, VIETNAMESE_STOP_WORDS
from app.algorithms.als_recommender import _compute_time_decay_weight

logger = logging.getLogger(__name__)
settings = get_settings()


def run_hybrid_recommendation_training(db: Session, alpha: float = None) -> dict:
    """
    Kích hoạt toàn bộ quy trình huấn luyện Gợi ý Lai ghép (Hybrid Recommender).

    Args:
        db: SQLAlchemy Session
        alpha: Trọng số Collaborative Filtering (mặc định lấy từ settings.HYBRID_ALPHA = 0.65)

    Returns:
        dict: Thống kê kết quả huấn luyện
    """
    if alpha is None:
        alpha = settings.HYBRID_ALPHA

    logger.info("=" * 60)
    logger.info(f"🚀 [Hybrid] Bắt đầu huấn luyện Gợi ý Lai ghép (Weighted Hybrid, α={alpha})...")
    logger.info("=" * 60)

    # ---------------------------------------------------------------
    # BƯỚC 1: Đọc sách active & Xây dựng ma trận TF-IDF Content-Based
    # ---------------------------------------------------------------
    active_books = db.query(Book).filter(Book.active == True).all()
    if len(active_books) < 2:
        msg = f"Không đủ sách active để tính toán (hiện có {len(active_books)})."
        logger.warning(f"⚠️ [Hybrid] {msg}")
        return {"status": "skipped", "reason": msg}

    category_ids = {b.category_id for b in active_books if b.category_id is not None}
    categories = {c.id: c.name for c in db.query(Category).filter(Category.id.in_(category_ids)).all()} if category_ids else {}

    book_id_list = [b.id for b in active_books]
    book_id_to_cbf_idx = {bid: idx for idx, bid in enumerate(book_id_list)}
    cbf_idx_to_book_id = {idx: bid for idx, bid in enumerate(book_id_list)}
    n_books = len(book_id_list)

    documents = [_build_book_document(b, categories.get(b.category_id, "")) for b in active_books]
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=settings.CBF_MAX_FEATURES,
        stop_words=VIETNAMESE_STOP_WORDS,
        sublinear_tf=True,
        strip_accents=None,
        analyzer="word",
        min_df=1
    )
    # tfidf_matrix shape: [n_books, n_features]
    tfidf_matrix = vectorizer.fit_transform(documents)
    # Chuẩn hóa L2 từng vector sách để dot-product chính là cosine similarity
    tfidf_normalized = normalize(tfidf_matrix, norm='l2', axis=1)
    logger.info(f"📚 [Hybrid/CBF] Đã vector hóa {n_books} sách active thành TF-IDF matrix: {tfidf_normalized.shape}")

    # ---------------------------------------------------------------
    # BƯỚC 2: Đọc tương tác người dùng & Đếm số tương tác mỗi sách
    # ---------------------------------------------------------------
    interactions = db.query(UserBookInteraction).all()
    if not interactions:
        msg = "Chưa có tương tác nào trong user_book_interactions."
        logger.warning(f"⚠️ [Hybrid] {msg}")
        return {"status": "skipped", "reason": msg}

    # Đếm số tương tác mỗi sách để tính tỷ lệ Cold-Start
    item_interaction_counts = {}
    for inter in interactions:
        item_interaction_counts[inter.book_id] = item_interaction_counts.get(inter.book_id, 0) + 1

    # Danh sách sách người dùng đã mua (BUY)
    bought_books = {}
    for inter in interactions:
        if inter.interaction_type == "BUY":
            bought_books.setdefault(inter.user_id, set()).add(inter.book_id)

    # ---------------------------------------------------------------
    # BƯỚC 3: Xây dựng ma trận tương tác thưa và huấn luyện mô hình Implicit ALS
    # ---------------------------------------------------------------
    now = datetime.now(timezone.utc)
    lam = settings.TIME_DECAY_LAMBDA

    # Tích lũy trọng số có Time-Decay theo (user_id, book_id)
    user_item_weights = {}
    user_history_books = {}  # user_id -> dict of {book_id: decayed_weight}

    for inter in interactions:
        decayed_w = _compute_time_decay_weight(
            weight_base=float(inter.weight),
            created_at=inter.created_at,
            now=now,
            lam=lam
        )
        key = (inter.user_id, inter.book_id)
        user_item_weights[key] = user_item_weights.get(key, 0.0) + decayed_w
        if inter.user_id not in user_history_books:
            user_history_books[inter.user_id] = {}
        user_history_books[inter.user_id][inter.book_id] = (
            user_history_books[inter.user_id].get(inter.book_id, 0.0) + decayed_w
        )

    # Áp dụng Log Saturation: R_ui = 1 + ln(1 + Σw)
    unique_users = sorted(list({k[0] for k in user_item_weights.keys()}))
    unique_books_in_interactions = sorted(list({k[1] for k in user_item_weights.keys()}))

    user_id_to_als_idx = {uid: idx for idx, uid in enumerate(unique_users)}
    als_idx_to_user_id = {idx: uid for idx, uid in enumerate(unique_users)}

    als_book_to_idx = {bid: idx for idx, bid in enumerate(unique_books_in_interactions)}
    als_idx_to_book = {idx: bid for idx, bid in enumerate(unique_books_in_interactions)}

    rows, cols, data = [], [], []
    for (uid, bid), raw_w in user_item_weights.items():
        rows.append(user_id_to_als_idx[uid])
        cols.append(als_book_to_idx[bid])
        data.append(1.0 + np.log(1.0 + raw_w))

    n_als_users = len(unique_users)
    n_als_items = len(unique_books_in_interactions)
    als_sparse_matrix = sparse.csr_matrix(
        (data, (rows, cols)),
        shape=(n_als_users, n_als_items),
        dtype=np.float32
    )

    logger.info(f"🤖 [Hybrid/ALS] Huấn luyện Implicit ALS trên ma trận: {n_als_users} users × {n_als_items} items...")
    als_model = AlternatingLeastSquares(
        factors=settings.ALS_FACTORS,
        regularization=settings.ALS_REGULARIZATION,
        iterations=settings.ALS_ITERATIONS,
        random_state=42
    )
    # Confidence: C_ui = 1 + alpha_als * R_ui
    confidence = (als_sparse_matrix * settings.ALS_ALPHA).astype(np.float32)
    als_model.fit(confidence, show_progress=False)
    logger.info("✅ [Hybrid/ALS] Huấn luyện Implicit ALS hoàn tất.")

    # ---------------------------------------------------------------
    # BƯỚC 4: Dự đoán điểm lai ghép (Hybrid Score) cho từng user
    # ---------------------------------------------------------------
    # Lấy danh sách real user IDs từ DB (tránh tài khoản ảo nếu có)
    real_user_rows = db.execute(text("SELECT id FROM users")).fetchall()
    real_user_ids = {r[0] for r in real_user_rows}

    cold_start_threshold = settings.ITEM_COLD_START_THRESHOLD
    top_k = settings.HYBRID_TOP_K
    active_book_ids_set = set(book_id_list)

    recommendation_records = []

    for user_id in unique_users:
        if user_id not in real_user_ids:
            continue

        user_bought = bought_books.get(user_id, set())
        user_history = user_history_books.get(user_id, {})
        if not user_history:
            continue

        # 4.1. TÍNH CONTENT-BASED SCORES CHO USER
        # Vector hồ sơ người dùng: p_u = sum_{b in history} w_b * v_b
        user_profile_vec = np.zeros(tfidf_normalized.shape[1], dtype=np.float32)
        total_hist_weight = 0.0
        for hid, hw in user_history.items():
            if hid in book_id_to_cbf_idx:
                c_idx = book_id_to_cbf_idx[hid]
                # Thêm vector sách có trọng số
                user_profile_vec += tfidf_normalized[c_idx].toarray().flatten() * hw
                total_hist_weight += hw

        if total_hist_weight > 0:
            user_profile_norm = np.linalg.norm(user_profile_vec)
            if user_profile_norm > 0:
                user_profile_vec /= user_profile_norm
            # Cosine similarity với toàn bộ active books
            # cbf_scores shape: [n_books]
            cbf_scores = tfidf_normalized.dot(user_profile_vec)
        else:
            cbf_scores = np.zeros(n_books, dtype=np.float32)

        # 4.2. TÍNH ALS SCORES CHO USER TRÊN TẤT CẢ ACTIVE BOOKS
        als_scores_raw = np.zeros(n_books, dtype=np.float32)
        if user_id in user_id_to_als_idx:
            u_idx = user_id_to_als_idx[user_id]
            u_factors = als_model.user_factors[u_idx]  # shape: [factors]

            for b_idx, bid in enumerate(book_id_list):
                if bid in als_book_to_idx:
                    i_als_idx = als_book_to_idx[bid]
                    i_factors = als_model.item_factors[i_als_idx]
                    als_scores_raw[b_idx] = float(np.dot(u_factors, i_factors))
                else:
                    # Item Cold-Start: sách mới chưa từng có tương tác trong ALS
                    als_scores_raw[b_idx] = 0.0

        # Min-Max Normalization cho ALS scores đưa về thang [0, 1]
        als_min = np.min(als_scores_raw)
        als_max = np.max(als_scores_raw)
        if als_max > als_min:
            als_scores_norm = (als_scores_raw - als_min) / (als_max - als_min)
        else:
            als_scores_norm = np.zeros_like(als_scores_raw)

        # 4.3. KẾT HỢP HYBRID VỚI TRỌNG SỐ ĐỘNG DYNAMIC ITEM CONFIDENCE
        hybrid_scores = []
        for b_idx, bid in enumerate(book_id_list):
            if bid in user_bought:
                continue  # Bỏ qua sách người dùng đã mua

            c_count = item_interaction_counts.get(bid, 0)
            # Tỷ lệ trưởng thành của item: gamma = min(1.0, count / threshold)
            gamma_i = min(1.0, float(c_count) / float(cold_start_threshold))
            effective_alpha = alpha * gamma_i

            score_als = float(als_scores_norm[b_idx])
            score_cbf = float(cbf_scores[b_idx])

            # Công thức lai ghép: alpha_i * ALS + (1 - alpha_i) * CBF
            h_score = (effective_alpha * score_als) + ((1.0 - effective_alpha) * score_cbf)
            hybrid_scores.append((bid, h_score))

        # Sắp xếp giảm dần theo điểm lai ghép
        hybrid_scores.sort(key=lambda x: x[1], reverse=True)

        # Lấy Top-K gợi ý
        for rank, (bid, score) in enumerate(hybrid_scores[:top_k], start=1):
            recommendation_records.append({
                "user_id": user_id,
                "book_id": bid,
                "recommendation_type": settings.RECOMMENDATION_TYPE,  # 'FOR_YOU'
                "algorithm": "HYBRID",
                "score": round(float(score), 6),
                "rank_order": rank,
                "updated_at": datetime.now()
            })

    logger.info(
        f"📊 [Hybrid] Đã sinh {len(recommendation_records)} bản ghi gợi ý lai ghép cho {len(unique_users)} users."
    )

    # ---------------------------------------------------------------
    # BƯỚC 5: Ghi đè vào bảng user_recommendations
    # ---------------------------------------------------------------
    deleted_count = (
        db.query(UserRecommendation)
        .filter(UserRecommendation.recommendation_type == settings.RECOMMENDATION_TYPE)
        .delete(synchronize_session=False)
    )
    logger.info(f"🗑️  [Hybrid] Đã xóa {deleted_count} bản ghi user_recommendations cũ (FOR_YOU).")

    if recommendation_records:
        db.bulk_insert_mappings(UserRecommendation, recommendation_records)
        db.commit()
        logger.info(f"💾 [Hybrid] Đã lưu {len(recommendation_records)} bản ghi mới vào user_recommendations.")
    else:
        db.rollback()
        logger.warning("⚠️  [Hybrid] Không có bản ghi nào để lưu.")

    result = {
        "status": "success",
        "algorithm": "HYBRID",
        "alpha_base": alpha,
        "users_processed": len(unique_users),
        "active_books_considered": n_books,
        "recommendations_written": len(recommendation_records),
        "top_k_per_user": top_k
    }
    logger.info(f"🎉 [Hybrid] Hoàn tất! Kết quả: {result}")
    return result
