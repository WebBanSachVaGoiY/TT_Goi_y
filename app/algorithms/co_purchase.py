"""
Thuật toán Item-Item Co-Purchase (Frequently Bought Together) cho BookRunner.

Luồng xử lý:
    1. Đọc các "giỏ hàng" từ bảng order_items JOIN orders (loại đơn CANCELLED/RETURNED)
    2. Với mỗi đơn có ≥ 2 sản phẩm, đếm số lần xuất hiện của từng cặp sách (a, b)
    3. Chuẩn hoá điểm tương đồng theo Cosine:
           score(a, b) = co_count(a, b) / sqrt(order_count(a) * order_count(b))
       → score ∈ [0, 1], ưu tiên cặp hay đi cùng nhau nhưng không thiên vị sách bán chạy
    4. Lấy Top-K cặp cho mỗi sách (2 chiều a→b và b→a để tra cứu từ bất kỳ sách nào)
    5. Ghi bulk vào bảng book_similarities với similarity_type='ALSO_BOUGHT'
       (xóa cũ trước để đảm bảo freshness)

Kết quả: bảng book_similarities với similarity_type='ALSO_BOUGHT'
"""
import os
import json
import logging
import math
from datetime import datetime
from collections import defaultdict
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models.recommendation import BookSimilarity
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Trạng thái đơn hàng KHÔNG tính vào co-purchase:
# - CANCELLED: đơn đã hủy
# - RETURNED:  đơn đã trả hàng/hoàn tiền
EXCLUDED_ORDER_STATUSES = ("CANCELLED", "RETURNED")


def _load_order_baskets(db: Session) -> dict:
    """
    Đọc tất cả giỏ hàng hợp lệ:
    1. Giỏ hàng THẬT từ bảng orders & order_items trong MariaDB.
    2. Giỏ hàng MẪU từ file ngoại tuyến data/synthetic_baskets.json (nếu có).
    """
    placeholders = ", ".join(f":st{i}" for i in range(len(EXCLUDED_ORDER_STATUSES)))
    params = {f"st{i}": s for i, s in enumerate(EXCLUDED_ORDER_STATUSES)}
    rows = db.execute(
        text(
            f"""
            SELECT oi.order_id AS order_id, oi.book_id AS book_id
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN books b ON b.id = oi.book_id
            WHERE o.status NOT IN ({placeholders})
              AND b.active = 1
            """
        ),
        params,
    ).fetchall()

    baskets = defaultdict(set)
    for row in rows:
        baskets[row.order_id].add(row.book_id)

    # Nạp thêm giỏ hàng mẫu từ file ngoại tuyến
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    baskets_file = os.path.join(base_dir, "data", "synthetic_baskets.json")
    if os.path.exists(baskets_file):
        try:
            with open(baskets_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded_synth = 0
            for idx, item in enumerate(data):
                b_ids = item.get("book_ids", [])
                if len(b_ids) >= 2:
                    baskets[f"synth_basket_{idx}"] = set(b_ids)
                    loaded_synth += 1
            logger.info(f"📁 [CoPurchase] Đã nạp thêm {loaded_synth} giỏ hàng mẫu từ file: {baskets_file}")
        except Exception as e:
            logger.warning(f"⚠️ [CoPurchase] Không thể đọc file giỏ hàng mẫu: {e}")

    return baskets


def run_co_purchase_training(db: Session) -> dict:
    """
    Kích hoạt toàn bộ pipeline Item-Item Co-Purchase (Frequently Bought Together).

    Args:
        db: SQLAlchemy Session đã được inject bởi FastAPI Depends

    Returns:
        dict: Thống kê kết quả huấn luyện
    """
    logger.info("=" * 60)
    logger.info("🚀 [CoPurchase] Bắt đầu tính toán Frequently Bought Together...")
    logger.info("=" * 60)

    # ---------------------------------------------------------------
    # BƯỚC 1: Đọc giỏ hàng từ order_items
    # ---------------------------------------------------------------
    baskets = _load_order_baskets(db)
    # Chỉ xét đơn có ≥ 2 sản phẩm (mới tạo được cặp co-purchase)
    multi_item_baskets = {oid: books for oid, books in baskets.items() if len(books) >= 2}

    if not multi_item_baskets:
        msg = (
            "Không có đơn hàng nào có ≥ 2 sản phẩm. "
            "FBT cần dữ liệu order_items thực tế (đơn từ Spring Boot)."
        )
        logger.warning(f"⚠️ [CoPurchase] {msg}")
        return {"status": "skipped", "reason": msg}

    logger.info(
        f"🧺 [CoPurchase] Đã tải {len(baskets)} đơn hàng, "
        f"trong đó {len(multi_item_baskets)} đơn có ≥ 2 sản phẩm."
    )

    # ---------------------------------------------------------------
    # BƯỚC 2: Đếm co-occurrence của từng cặp sách + số đơn chứa mỗi sách
    # ---------------------------------------------------------------
    pair_count: dict[tuple[int, int], int] = defaultdict(int)
    book_order_count: dict[int, int] = defaultdict(int)

    for books in multi_item_baskets.values():
        book_list = sorted(books)
        for b in book_list:
            book_order_count[b] += 1
        # Mọi cặp không thứ tự (a < b) trong cùng một đơn
        for i in range(len(book_list)):
            for j in range(i + 1, len(book_list)):
                pair_count[(book_list[i], book_list[j])] += 1

    logger.info(
        f"📊 [CoPurchase] {len(pair_count)} cặp sách co-purchase, "
        f"{len(book_order_count)} sách xuất hiện trong đơn."
    )

    # ---------------------------------------------------------------
    # BƯỚC 3: Lọc nhiễu (min_count) + tính điểm Cosine-normalized
    # ---------------------------------------------------------------
    min_count = settings.CO_PURCHASE_MIN_COUNT
    # adjacency[a] = list of (b, score, count)
    adjacency: dict[int, list[tuple[int, float, int]]] = defaultdict(list)

    for (a, b), cnt in pair_count.items():
        if cnt < min_count:
            continue
        denom = math.sqrt(book_order_count[a] * book_order_count[b])
        score = cnt / denom if denom > 0 else 0.0
        adjacency[a].append((b, score, cnt))
        adjacency[b].append((a, score, cnt))

    top_k = settings.CO_PURCHASE_TOP_K
    similarity_type = settings.CO_PURCHASE_SIMILARITY_TYPE
    similarity_records = []

    for source_book_id, neighbors in adjacency.items():
        # Sắp xếp theo điểm giảm dần, tie-break theo số lần co-purchase
        neighbors.sort(key=lambda x: (x[1], x[2]), reverse=True)
        for rank, (target_book_id, score, _cnt) in enumerate(neighbors[:top_k]):
            similarity_records.append({
                "book_id_1": source_book_id,
                "book_id_2": target_book_id,
                "similarity_type": similarity_type,
                "score": round(float(score), 6),
                "rank_order": rank + 1,
                "updated_at": datetime.now()
            })

    logger.info(
        f"📊 [CoPurchase] Tạo {len(similarity_records)} bản ghi (top_{top_k} mỗi sách)."
    )

    # ---------------------------------------------------------------
    # BƯỚC 4: Ghi DB — xóa cũ trước, bulk insert mới
    # ---------------------------------------------------------------
    deleted_count = (
        db.query(BookSimilarity)
        .filter(BookSimilarity.similarity_type == similarity_type)
        .delete(synchronize_session=False)
    )
    logger.info(f"🗑️  [CoPurchase] Đã xóa {deleted_count} bản ghi book_similarities cũ (ALSO_BOUGHT).")

    if similarity_records:
        db.bulk_insert_mappings(BookSimilarity, similarity_records)
        db.commit()
        logger.info(f"💾 [CoPurchase] Đã ghi {len(similarity_records)} bản ghi mới vào book_similarities.")
    else:
        db.rollback()
        logger.warning("⚠️  [CoPurchase] Không có bản ghi nào để ghi.")

    result = {
        "status": "success",
        "orders_processed": len(baskets),
        "multi_item_orders": len(multi_item_baskets),
        "distinct_pair_count": len(pair_count),
        "similarity_pairs_written": len(similarity_records),
        "top_k_per_book": top_k,
        "min_count": min_count,
    }
    logger.info(f"🎉 [CoPurchase] Hoàn thành! Kết quả: {result}")
    return result
