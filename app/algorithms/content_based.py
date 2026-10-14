"""
Thuật toán Content-Based Filtering cho hệ thống gợi ý sách BookRunner.

Luồng xử lý:
    1. Đọc dữ liệu sách active từ MariaDB (bảng books + categories)
    2. Xây dựng 'hồ sơ văn bản' cho từng cuốn sách bằng cách ghép metadata
       có trọng số: Document_i = (Title×2) + (Author×2) + (Category×3) + Description
    3. Tính vector TF-IDF cho mỗi cuốn sách (5000 features, ngram 1-2)
    4. Tính ma trận Cosine Similarity (N×N) giữa tất cả cặp sách
    5. Trích xuất Top-K sách tương tự nhất cho từng cuốn (bỏ qua chính mình)
    6. Ghi bulk vào bảng book_similarities (xóa cũ trước để đảm bảo freshness)

Kết quả: bảng book_similarities với similarity_type='CONTENT_BASED'
"""
import logging
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session
from app.models.book import Book, Category
from app.models.recommendation import BookSimilarity
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Từ dừng tiếng Việt phổ biến — bỏ qua khi tính TF-IDF
VIETNAMESE_STOP_WORDS = [
    "là", "của", "và", "các", "những", "cuốn", "sách", "với", "được",
    "trong", "về", "cho", "bởi", "hay", "đã", "có", "một", "này", "đến",
    "từ", "để", "như", "khi", "nếu", "thì", "mà", "rất", "tác", "giả",
    "phẩm", "nội", "dung", "thông", "tin", "truyện", "cũng", "đây",
    "người", "đọc", "qua", "sau", "trước", "theo", "lại", "bằng"
]


def _build_book_document(book: Book, category_name: str) -> str:
    """
    Xây dựng 'hồ sơ văn bản' cho một cuốn sách theo công thức có trọng số:
        Document_i = (Title × 2) + (Author × 2) + (Category × 3) + Description

    Lặp lại trường quan trọng để tăng tần suất → TF-IDF sẽ phân biệt tốt hơn.
    """
    parts = []

    # Title × 2 (tiêu đề phân biệt cuốn sách)
    if book.title:
        parts.extend([book.title] * 2)

    # Author × 2 (tác giả giúp cluster sách cùng tác giả)
    if book.author:
        parts.extend([book.author] * 2)

    # Category × 3 (thể loại là đặc trưng quan trọng nhất)
    if category_name:
        parts.extend([category_name] * 3)

    # Description × 1 (nội dung mô tả — ít trọng số hơn vì dài và nhiều từ chung)
    if book.description:
        parts.append(book.description)

    return " ".join(parts)


def run_content_based_training(db: Session) -> dict:
    """
    Kích hoạt toàn bộ pipeline Content-Based Filtering.

    Args:
        db: SQLAlchemy Session đã được inject bởi FastAPI Depends

    Returns:
        dict: Thống kê kết quả huấn luyện
    """
    logger.info("=" * 60)
    logger.info("🚀 [CBF] Bắt đầu huấn luyện Content-Based Filtering...")
    logger.info("=" * 60)

    # ---------------------------------------------------------------
    # BƯỚC 1: Đọc dữ liệu sách active từ DB
    # ---------------------------------------------------------------
    books = db.query(Book).filter(Book.active == True).all()
    if len(books) < 2:
        msg = f"Không đủ sách để tính toán (cần ≥ 2, hiện có {len(books)})."
        logger.warning(f"⚠️ [CBF] {msg}")
        return {"status": "skipped", "reason": msg}

    # Tải mapping category_id → category_name
    category_ids = {b.category_id for b in books if b.category_id is not None}
    categories: dict[int, str] = {}
    if category_ids:
        cat_list = db.query(Category).filter(Category.id.in_(category_ids)).all()
        categories = {c.id: c.name for c in cat_list}

    logger.info(f"📚 [CBF] Đã tải {len(books)} sách từ {len(categories)} danh mục.")

    # ---------------------------------------------------------------
    # BƯỚC 2: Xây dựng corpus văn bản
    # ---------------------------------------------------------------
    book_ids = [b.id for b in books]
    documents = [
        _build_book_document(b, categories.get(b.category_id, ""))
        for b in books
    ]

    # ---------------------------------------------------------------
    # BƯỚC 3: TF-IDF Vectorization
    # ---------------------------------------------------------------
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),                     # Bắt từ đơn + cụm 2 từ: "lập trình", "machine learning"
        max_features=settings.CBF_MAX_FEATURES, # Giới hạn vocabulary 5000 từ phân biệt nhất
        stop_words=VIETNAMESE_STOP_WORDS,
        sublinear_tf=True,                      # Dùng log(1+TF) thay vì TF thô — giảm dominance của từ lặp nhiều
        strip_accents=None,                     # Giữ nguyên dấu tiếng Việt (không normalize)
        analyzer="word",
        min_df=1                                # Giữ từ xuất hiện ít nhất 1 lần
    )
    tfidf_matrix = vectorizer.fit_transform(documents)
    logger.info(f"🔢 [CBF] TF-IDF matrix: {tfidf_matrix.shape[0]} sách × {tfidf_matrix.shape[1]} features")

    # ---------------------------------------------------------------
    # BƯỚC 4: Tính Cosine Similarity
    # cosine_similarity(A, B) = (A·B) / (‖A‖ × ‖B‖), kết quả ∈ [0, 1]
    # ---------------------------------------------------------------
    sim_matrix = cosine_similarity(tfidf_matrix, tfidf_matrix)
    logger.info(f"✅ [CBF] Cosine Similarity matrix: {sim_matrix.shape}")

    # ---------------------------------------------------------------
    # BƯỚC 5: Trích xuất Top-K sách tương tự nhất
    # ---------------------------------------------------------------
    top_k = settings.CBF_TOP_K
    similarity_records = []

    for i, book_id in enumerate(book_ids):
        # Copy để không làm bẩn ma trận gốc
        sim_scores = sim_matrix[i].copy()
        # Loại bỏ chính mình (đặt điểm = -1 để argsort đẩy xuống cuối)
        sim_scores[i] = -1.0

        # Sắp xếp giảm dần, lấy top_k index
        top_indices = np.argsort(sim_scores)[::-1][:top_k]

        for rank, j in enumerate(top_indices):
            score = float(sim_scores[j])
            if score <= 0.0:
                continue  # Bỏ qua các cặp không có điểm tương đồng
            similarity_records.append({
                "book_id_1": book_id,
                "book_id_2": book_ids[j],
                "similarity_type": settings.CBF_SIMILARITY_TYPE,
                "score": round(score, 6),
                "rank_order": rank + 1
            })

    logger.info(f"📊 [CBF] Tính được {len(similarity_records)} cặp tương đồng (top_{top_k} × {len(books)} sách).")

    # ---------------------------------------------------------------
    # BƯỚC 6: Ghi vào DB — xóa cũ trước, bulk insert mới
    # Composite PK (book_id_1, book_id_2, similarity_type) — không dùng UPSERT
    # vì SQLAlchemy không hỗ trợ ON DUPLICATE KEY UPDATE cho composite PK tốt
    # ---------------------------------------------------------------
    deleted_count = (
        db.query(BookSimilarity)
        .filter(BookSimilarity.similarity_type == settings.CBF_SIMILARITY_TYPE)
        .delete(synchronize_session=False)
    )
    logger.info(f"🗑️  [CBF] Đã xóa {deleted_count} bản ghi book_similarities cũ (CONTENT_BASED).")

    if similarity_records:
        db.bulk_insert_mappings(BookSimilarity, similarity_records)
        db.commit()
        logger.info(f"💾 [CBF] Đã ghi {len(similarity_records)} bản ghi mới vào book_similarities.")
    else:
        db.rollback()
        logger.warning("⚠️  [CBF] Không có bản ghi nào để ghi (tất cả điểm = 0).")

    result = {
        "status": "success",
        "books_processed": len(books),
        "similarity_pairs_written": len(similarity_records),
        "top_k_per_book": top_k,
        "tfidf_features": tfidf_matrix.shape[1],
    }
    logger.info(f"🎉 [CBF] Hoàn thành! Kết quả: {result}")
    return result
