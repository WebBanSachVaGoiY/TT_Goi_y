"""
Thuật toán Collaborative Filtering ALS (Alternating Least Squares) với Implicit Feedback cho BookRunner.

Luồng xử lý:
    1. Đọc toàn bộ user_book_interactions từ DB
    2. Áp dụng Time-Decay: w(e) = w_base × exp(-λ × Δt)
       với λ=0.05 (chu kỳ bán rã ~14 ngày)
    3. Tổng hợp theo cặp (user, book) và áp dụng Log Saturation:
       R_ui = 1 + ln(1 + Σw) — triệt tiêu spam tương tác
    4. Xây dựng ma trận thưa User-Item (scipy.sparse CSR)
    5. Huấn luyện Implicit ALS: Confidence c_ui = 1 + α×R_ui (α=40)
       Tối thiểu hóa: Σ c_ui(p_ui - x_u^T y_i)^2 + λ_reg(‖X‖² + ‖Y‖²)
    6. Dự đoán top-K sách gợi ý cho từng user (bỏ sách đã BUY)
    7. Ghi bulk vào bảng user_recommendations

Kết quả: bảng user_recommendations với recommendation_type='FOR_YOU', algorithm='ALS'
"""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
import logging
import numpy as np
import scipy.sparse as sparse
from datetime import datetime, timezone
from implicit.als import AlternatingLeastSquares
from sqlalchemy.orm import Session
from app.models.interaction import UserBookInteraction
from app.models.recommendation import UserRecommendation
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _compute_time_decay_weight(
    weight_base: float,
    created_at: datetime,
    now: datetime,
    lam: float
) -> float:
    """
    Công thức suy giảm thời gian (Time-Decay Exponential):
        w(e) = w_base × exp(-λ × Δt)

    Ví dụ với λ=0.05:
        - Hành vi 0 ngày trước: w = w_base × 1.0   (không suy giảm)
        - Hành vi 14 ngày trước: w ≈ w_base × 0.5  (giảm 50%)
        - Hành vi 60 ngày trước: w ≈ w_base × 0.05 (giảm 95%)
    """
    # Chuẩn hóa timezone để tránh TypeError khi so sánh naive vs aware datetime
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delta_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    return float(weight_base) * np.exp(-lam * delta_days)


def _build_interaction_matrix(interactions: list) -> tuple:
    """
    Xây dựng ma trận tương tác thưa User-Item với Time-Decay + Log Saturation.

    Công thức tổng hợp:
        R_ui = 1 + ln(1 + Σ_e w(e))

    Sử dụng scipy CSR sparse matrix để tiết kiệm bộ nhớ với dữ liệu thưa thớt.

    Returns:
        tuple: (
            sparse_matrix (CSR, shape=[n_users, n_items]),
            user_id_to_idx (dict: DB user_id → ma trận row idx),
            book_id_to_idx (dict: DB book_id → ma trận col idx),
            idx_to_user_id (dict: row idx → DB user_id),
            idx_to_book_id (dict: col idx → DB book_id)
        )
    """
    now = datetime.now(timezone.utc)
    lam = settings.TIME_DECAY_LAMBDA

    # Tích lũy trọng số theo cặp (user_id, book_id)
    weight_accumulator: dict[tuple, float] = {}
    for interaction in interactions:
        key = (interaction.user_id, interaction.book_id)
        decayed_w = _compute_time_decay_weight(
            weight_base=float(interaction.weight),
            created_at=interaction.created_at,
            now=now,
            lam=lam
        )
        weight_accumulator[key] = weight_accumulator.get(key, 0.0) + decayed_w

    if not weight_accumulator:
        return None, {}, {}, {}, {}

    # Ánh xạ user_id / book_id sang chỉ số ma trận liên tục
    all_user_ids = sorted(set(k[0] for k in weight_accumulator.keys()))
    all_book_ids = sorted(set(k[1] for k in weight_accumulator.keys()))

    user_id_to_idx = {uid: i for i, uid in enumerate(all_user_ids)}
    book_id_to_idx = {bid: i for i, bid in enumerate(all_book_ids)}
    idx_to_user_id = {i: uid for uid, i in user_id_to_idx.items()}
    idx_to_book_id = {i: bid for bid, i in book_id_to_idx.items()}

    # Xây dựng sparse matrix với Log Saturation
    rows, cols, data = [], [], []
    for (user_id, book_id), sum_weight in weight_accumulator.items():
        # R_ui = 1 + ln(1 + sum_weight)
        # np.log1p(x) = ln(1+x), ổn định hơn np.log(1+x) khi x rất nhỏ
        r_ui = 1.0 + np.log1p(sum_weight)
        rows.append(user_id_to_idx[user_id])
        cols.append(book_id_to_idx[book_id])
        data.append(r_ui)

    n_users = len(all_user_ids)
    n_items = len(all_book_ids)
    sparse_matrix = sparse.csr_matrix(
        (data, (rows, cols)),
        shape=(n_users, n_items),
        dtype=np.float32
    )

    sparsity = 100.0 * (1.0 - sparse_matrix.nnz / (n_users * n_items))
    logger.info(
        f"📐 [ALS] Ma trận tương tác: {n_users} users × {n_items} items | "
        f"{sparse_matrix.nnz} điểm dữ liệu | Sparsity: {sparsity:.2f}%"
    )

    return sparse_matrix, user_id_to_idx, book_id_to_idx, idx_to_user_id, idx_to_book_id


def run_collaborative_filtering_training(db: Session) -> dict:
    """
    Kích hoạt toàn bộ pipeline Collaborative Filtering ALS với Implicit Feedback.

    Args:
        db: SQLAlchemy Session đã được inject bởi FastAPI Depends

    Returns:
        dict: Thống kê kết quả huấn luyện
    """
    logger.info("=" * 60)
    logger.info("🚀 [ALS] Bắt đầu huấn luyện Collaborative Filtering ALS...")
    logger.info("=" * 60)

    # ---------------------------------------------------------------
    # BƯỚC 1: Đọc toàn bộ dữ liệu tương tác
    # ---------------------------------------------------------------
    interactions = db.query(UserBookInteraction).all()
    if not interactions:
        msg = "Bảng user_book_interactions trống. Cần chạy seed_synthetic_data.py trước."
        logger.warning(f"⚠️ [ALS] {msg}")
        return {"status": "skipped", "reason": msg}

    logger.info(f"📝 [ALS] Đã tải {len(interactions)} bản ghi tương tác.")

    # ---------------------------------------------------------------
    # BƯỚC 2 & 3: Xây dựng ma trận tương tác (Time-Decay + Log Saturation)
    # ---------------------------------------------------------------
    (
        sparse_matrix,
        user_id_to_idx,
        book_id_to_idx,
        idx_to_user_id,
        idx_to_book_id
    ) = _build_interaction_matrix(interactions)

    if sparse_matrix is None:
        return {"status": "skipped", "reason": "Ma trận tương tác rỗng sau khi xử lý."}

    # ---------------------------------------------------------------
    # BƯỚC 4: Xác định sách đã BUY của từng user (để loại bỏ khỏi gợi ý)
    # Không gợi ý sách người dùng đã mua — tránh redundant recommendations
    # ---------------------------------------------------------------
    bought_books: dict[int, set] = {}
    for interaction in interactions:
        if interaction.interaction_type == "BUY":
            if interaction.user_id not in bought_books:
                bought_books[interaction.user_id] = set()
            bought_books[interaction.user_id].add(interaction.book_id)

    # ---------------------------------------------------------------
    # BƯỚC 5: Huấn luyện Implicit ALS
    # Trong implicit >= 0.5, model.fit() nhận trực tiếp User-Item matrix (shape: [n_users, n_items])
    # ---------------------------------------------------------------
    import threadpoolctl
    with threadpoolctl.threadpool_limits(1, "blas"):
        model = AlternatingLeastSquares(
            factors=settings.ALS_FACTORS,           # K = 32 chiều ẩn
            iterations=settings.ALS_ITERATIONS,     # 15 epoch
            regularization=settings.ALS_REGULARIZATION,  # λ_reg = 0.1
            alpha=settings.ALS_ALPHA,               # α = 40 → c_ui = 1 + 40×R_ui
            calculate_training_loss=False,          # Tắt để tăng tốc
            random_state=42,
            use_gpu=False                           # Không yêu cầu GPU
        )

        logger.info(
            f"⚙️  [ALS] Huấn luyện với: factors={settings.ALS_FACTORS}, "
            f"iterations={settings.ALS_ITERATIONS}, alpha={settings.ALS_ALPHA}"
        )
        model.fit(sparse_matrix)
    logger.info("✅ [ALS] Huấn luyện ALS hoàn tất.")

    # ---------------------------------------------------------------
    # BƯỚC 6: Dự đoán gợi ý Top-K cho từng user
    # ---------------------------------------------------------------
    top_k = settings.ALS_TOP_K
    n_users = sparse_matrix.shape[0]
    recommendation_records = []

    for user_idx in range(n_users):
        user_id = idx_to_user_id[user_idx]
        user_bought = bought_books.get(user_id, set())

        # Lấy nhiều hơn top_k để sau khi filter BUY vẫn đủ, nhưng không vượt quá tổng số items
        n_fetch = min(sparse_matrix.shape[1], top_k + len(user_bought) + 10)

        try:
            # model.recommend trả về (item_indices, scores), sorted by score DESC
            item_ids_arr, scores_arr = model.recommend(
                userid=user_idx,
                user_items=sparse_matrix[user_idx],
                N=n_fetch,
                filter_already_liked_items=False  # Tự filter để kiểm soát chính xác
            )
        except Exception as e:
            logger.warning(f"⚠️ [ALS] Không tạo được gợi ý cho user_idx={user_idx}: {e}")
            continue

        rank = 1
        seen_book_ids = set(user_bought)
        for item_idx_raw, score in zip(item_ids_arr, scores_arr):
            if rank > top_k:
                break
            # item_idx có thể là numpy int — cần cast sang Python int
            book_id = idx_to_book_id.get(int(item_idx_raw))
            if book_id is None:
                continue
            if book_id in seen_book_ids:
                continue  # Bỏ qua sách đã mua hoặc đã được đưa vào gợi ý
            seen_book_ids.add(book_id)

            recommendation_records.append({
                "user_id": user_id,
                "book_id": book_id,
                "recommendation_type": settings.RECOMMENDATION_TYPE,  # 'FOR_YOU'
                "algorithm": settings.ALGORITHM_NAME,                  # 'ALS'
                "score": float(score),
                "rank_order": rank
            })
            rank += 1

    logger.info(
        f"📊 [ALS] Đã tạo {len(recommendation_records)} bản ghi gợi ý cho {n_users} users."
    )

    # ---------------------------------------------------------------
    # BƯỚC 7: Ghi vào DB — xóa cũ trước, bulk insert mới
    # ---------------------------------------------------------------
    deleted_count = (
        db.query(UserRecommendation)
        .filter(UserRecommendation.recommendation_type == settings.RECOMMENDATION_TYPE)
        .delete(synchronize_session=False)
    )
    logger.info(f"🗑️  [ALS] Đã xóa {deleted_count} bản ghi user_recommendations cũ (FOR_YOU).")

    if recommendation_records:
        db.bulk_insert_mappings(UserRecommendation, recommendation_records)
        db.commit()
        logger.info(f"💾 [ALS] Đã ghi {len(recommendation_records)} bản ghi mới vào user_recommendations.")
    else:
        db.rollback()
        logger.warning("⚠️  [ALS] Không có bản ghi nào để ghi.")

    result = {
        "status": "success",
        "users_processed": n_users,
        "items_in_matrix": sparse_matrix.shape[1],
        "total_interactions": len(interactions),
        "recommendations_written": len(recommendation_records),
        "top_k_per_user": top_k,
    }
    logger.info(f"🎉 [ALS] Hoàn thành! Kết quả: {result}")
    return result
