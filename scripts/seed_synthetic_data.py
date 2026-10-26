"""
Script sinh tập dữ liệu huấn luyện mẫu (Synthetic Offline Datasets) cho RecSys BookRunner.
Theo kiến trúc Clean Architecture:
- Dữ liệu giả lập được lưu vào file offline (data/synthetic_interactions.json & data/synthetic_baskets.json).
- HOÀN TOÀN KHÔNG CHÈN tài khoản ảo vào bảng 'users'.
- HOÀN TOÀN KHÔNG CHÈN đơn hàng rác vào bảng 'orders'.
- Giữ cơ sở dữ liệu MariaDB sạch 100% cho Dashboard Admin.
"""
import sys
import os
import json
import random
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal
from app.models.book import Book, Category

random.seed(42)

# =====================================================================
# CẤU HÌNH 4 PERSONA CLUSTERS
# =====================================================================
PERSONA_CLUSTERS = [
    {
        "name": "Cluster 1: Developer / Tech",
        "preferred_slugs": ["lap-trinh-cntt"],
        "behavior": {
            "VIEW": (6, 15),
            "ADD_TO_CART": (2, 5),
            "BUY": (1, 3),
        }
    },
    {
        "name": "Cluster 2: Kinh Doanh / Khởi Nghiệp",
        "preferred_slugs": ["kinh-te-khoi-nghiep"],
        "behavior": {
            "VIEW": (5, 12),
            "ADD_TO_CART": (1, 4),
            "BUY": (1, 2),
        }
    },
    {
        "name": "Cluster 3: Văn Học & Tiểu Thuyết",
        "preferred_slugs": ["van-hoc-tieu-thuyet"],
        "behavior": {
            "VIEW": (6, 16),
            "ADD_TO_CART": (1, 3),
            "BUY": (0, 2),
        }
    },
    {
        "name": "Cluster 4: Kỹ Năng Sống & Phát Triển Bản Thân",
        "preferred_slugs": ["ky-nang-song"],
        "behavior": {
            "VIEW": (5, 14),
            "ADD_TO_CART": (2, 4),
            "BUY": (1, 3),
        }
    },
    {
        "name": "Cluster 5: Khoa Học & Đời Sống",
        "preferred_slugs": ["khoa-hoc-doi-song"],
        "behavior": {
            "VIEW": (5, 12),
            "ADD_TO_CART": (1, 3),
            "BUY": (1, 2),
        }
    },
    {
        "name": "Cluster 6: Tâm Lý Học",
        "preferred_slugs": ["tam-ly-hoc"],
        "behavior": {
            "VIEW": (6, 14),
            "ADD_TO_CART": (2, 4),
            "BUY": (1, 2),
        }
    },
    {
        "name": "Cluster 7: Thiếu Nhi & Gia Đình",
        "preferred_slugs": ["thieu-nhi"],
        "behavior": {
            "VIEW": (5, 12),
            "ADD_TO_CART": (2, 5),
            "BUY": (1, 3),
        }
    },
]

INTERACTION_WEIGHTS = {
    "VIEW": 1.0,
    "ADD_TO_CART": 3.0,
    "BUY": 5.0,
}

DAYS_RANGE = 60
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def random_iso_timestamp(days_back: int) -> str:
    """Sinh chuỗi thời gian ISO rải đều ngẫu nhiên trong khoảng days_back ngày."""
    offset_seconds = random.uniform(0, days_back * 86400)
    dt = datetime.now(timezone.utc) - timedelta(seconds=offset_seconds)
    return dt.isoformat()


def main():
    print("=" * 70)
    print("🌱 BOOKRUNNER SYNTHETIC DATASET GENERATOR (CLEAN ARCHITECTURE)")
    print("=" * 70)
    print("💡 Chế độ: Xuất tập dữ liệu ra File JSON ngoại tuyến (Không làm bẩn DB)")

    os.makedirs(DATA_DIR, exist_ok=True)
    db = SessionLocal()

    try:
        # 1. Tải danh sách sách active từ DB
        all_books = db.query(Book).filter(Book.active == True).all()
        if not all_books:
            print("❌ Không tìm thấy sách active nào trong DB!")
            print("   Vui lòng khởi động Spring Boot (book-runner) trước để tạo sách mẫu.")
            return

        categories = {c.id: c.slug for c in db.query(Category).all()}
        books_by_slug: dict[str, list] = {}
        for book in all_books:
            slug = categories.get(book.category_id, "unknown")
            if slug not in books_by_slug:
                books_by_slug[slug] = []
            books_by_slug[slug].append(book)

        print(f"\n📚 Đã tải {len(all_books)} sách đang bán từ MariaDB.")

        # 2. Lấy danh sách người dùng THẬT từ bảng users
        real_users = db.execute(
            text("SELECT id, username FROM users WHERE role = 'ROLE_CUSTOMER' ORDER BY id ASC")
        ).fetchall()
        print(f"👥 Đã phát hiện {len(real_users)} tài khoản khách hàng THẬT trong DB.")

        # 3. Phân bổ User: Gồm Users THẬT + 50 Virtual Persona Users (ID từ 10001 -> 10050)
        # Gán các user thật vào các cluster tương ứng
        user_assignments = []
        for idx, (uid, uname) in enumerate(real_users):
            cluster = PERSONA_CLUSTERS[idx % len(PERSONA_CLUSTERS)]
            user_assignments.append((uid, cluster, True))  # True = User Thật

        # Thêm 50 Virtual Users để ma trận ALS có đủ chiều sâu học đa dạng
        for i in range(1, 51):
            virtual_id = 10000 + i
            cluster = PERSONA_CLUSTERS[(i - 1) % len(PERSONA_CLUSTERS)]
            user_assignments.append((virtual_id, cluster, False))  # False = User Ảo

        print(f"🎯 Tổng cộng: {len(user_assignments)} độc giả được mô phỏng ({len(real_users)} thật + 50 ảo).")

        # 4. Sinh tập dữ liệu tương tác (Interactions)
        interactions_dataset = []
        print("\n⚙️ Đang tổng hợp dữ liệu tương tác theo hành vi Persona...")

        for uid, cluster, is_real in user_assignments:
            pref_books = []
            for slug in cluster["preferred_slugs"]:
                pref_books.extend(books_by_slug.get(slug, []))

            non_pref_books = [b for b in all_books if b not in pref_books]
            if not pref_books:
                pref_books = all_books

            # User tương tác nhiều với sách sở thích và 1-2 sách ngoài sở thích
            sample_count = min(len(non_pref_books), max(1, len(pref_books) // 2))
            target_books = pref_books + random.sample(non_pref_books, sample_count)

            for book in target_books:
                is_pref = book in pref_books

                # VIEW
                view_range = (6, 14) if is_pref else (1, 3)
                for _ in range(random.randint(*view_range)):
                    interactions_dataset.append({
                        "user_id": uid,
                        "book_id": book.id,
                        "interaction_type": "VIEW",
                        "weight": INTERACTION_WEIGHTS["VIEW"],
                        "explicit_rating": None,
                        "created_at": random_iso_timestamp(DAYS_RANGE),
                        "is_virtual_user": not is_real
                    })

                # ADD_TO_CART
                if random.random() < (0.75 if is_pref else 0.15):
                    for _ in range(random.randint(1, 4 if is_pref else 1)):
                        interactions_dataset.append({
                            "user_id": uid,
                            "book_id": book.id,
                            "interaction_type": "ADD_TO_CART",
                            "weight": INTERACTION_WEIGHTS["ADD_TO_CART"],
                            "explicit_rating": None,
                            "created_at": random_iso_timestamp(DAYS_RANGE),
                            "is_virtual_user": not is_real
                        })

                # BUY
                has_bought = False
                if random.random() < (0.60 if is_pref else 0.05):
                    has_bought = True
                    for _ in range(random.randint(1, 2)):
                        interactions_dataset.append({
                            "user_id": uid,
                            "book_id": book.id,
                            "interaction_type": "BUY",
                            "weight": INTERACTION_WEIGHTS["BUY"],
                            "explicit_rating": None,
                            "created_at": random_iso_timestamp(DAYS_RANGE),
                            "is_virtual_user": not is_real
                        })

                # RATING
                if has_bought and random.random() < 0.70:
                    rating_val = random.choice([4, 5]) if is_pref else random.choice([2, 3])
                    interactions_dataset.append({
                        "user_id": uid,
                        "book_id": book.id,
                        "interaction_type": "RATING",
                        "weight": float(rating_val),
                        "explicit_rating": rating_val,
                        "created_at": random_iso_timestamp(DAYS_RANGE),
                        "is_virtual_user": not is_real
                    })

        # Lưu vào file JSON
        interactions_file = os.path.join(DATA_DIR, "synthetic_interactions.json")
        with open(interactions_file, "w", encoding="utf-8") as f:
            json.dump(interactions_dataset, f, ensure_ascii=False, indent=2)

        print(f"💾 Đã lưu {len(interactions_dataset)} bản ghi tương tác vào:")
        print(f"   -> {interactions_file}")

        # 5. Sinh tập dữ liệu giỏ hàng mẫu (Baskets) cho Co-Purchase FBT
        baskets_dataset = []
        print("\n🧺 Đang tổng hợp giỏ hàng mẫu cho Co-Purchase (FBT)...")

        basket_id = 1
        for cluster in PERSONA_CLUSTERS:
            pref_books = []
            for slug in cluster["preferred_slugs"]:
                pref_books.extend(books_by_slug.get(slug, []))

            if len(pref_books) < 2:
                continue

            # Mỗi cluster sinh 30 giỏ hàng gồm 2-4 cuốn sách hay mua cùng
            for _ in range(30):
                basket_size = min(len(pref_books), random.randint(2, 4))
                chosen = random.sample(pref_books, basket_size)
                baskets_dataset.append({
                    "basket_id": f"BASKET-{basket_id:04d}",
                    "cluster": cluster["name"],
                    "book_ids": [b.id for b in chosen]
                })
                basket_id += 1

        baskets_file = os.path.join(DATA_DIR, "synthetic_baskets.json")
        with open(baskets_file, "w", encoding="utf-8") as f:
            json.dump(baskets_dataset, f, ensure_ascii=False, indent=2)

        print(f"💾 Đã lưu {len(baskets_dataset)} giỏ hàng mẫu vào:")
        print(f"   -> {baskets_file}")

        print("\n" + "=" * 70)
        print("🎉 XUẤT DATASET HOÀN TẤT THÀNH CÔNG!")
        print("   - Cơ sở dữ liệu MariaDB: 0 byte rác (Bảng users & orders sạch 100%)")
        print("   - Khi chạy huấn luyện, FastAPI sẽ tự động nạp các file này vào RAM.")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ LỖI KHI XUẤT DATASET: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
