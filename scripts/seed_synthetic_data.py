"""
Script sinh dữ liệu tương tác giả lập phục vụ kiểm chứng thuật toán RecSys (BookRunner).

Chiến lược sinh dữ liệu theo đặc tả RECSYS_DOCUMENTATION.md:
- 4 Persona Clusters:
    1. Developer / Tech (Lập trình, AI, DevOps)
    2. Kinh Doanh / Tài Chính (Kinh tế, Khởi nghiệp, Đầu tư)
    3. Văn Học / Nghệ Thuật (Tiểu thuyết, Văn học kinh điển)
    4. Kỹ Năng / Tâm Lý (Kỹ năng sống, Phát triển bản thân)
- 50 synthetic users (hoặc phân bổ trên danh sách users hiện có)
- 4.000 – 6.000 bản ghi tương tác với timestamp rải đều trong 60 ngày gần nhất
- Đảm bảo mỗi cluster tập trung 80% tương tác vào thể loại ưa thích để mô hình ALS học được mẫu hành vi
"""
import sys
import os
import random
from datetime import datetime, timedelta, timezone

# Đưa thư mục gốc TT_Goi_y vào sys.path để import được app/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal
from app.models.book import Book, Category
from app.models.interaction import UserBookInteraction

random.seed(42)

# =====================================================================
# CẤU HÌNH 4 PERSONA CLUSTERS
# =====================================================================
PERSONA_CLUSTERS = [
    {
        "name": "Cluster 1: Developer / Tech",
        "preferred_slugs": ["lap-trinh-cntt"],
        "behavior": {
            "VIEW": (4, 10),
            "ADD_TO_CART": (1, 4),
            "BUY": (0, 2),
        }
    },
    {
        "name": "Cluster 2: Kinh Doanh / Tài Chính",
        "preferred_slugs": ["kinh-te-khoi-nghiep"],
        "behavior": {
            "VIEW": (3, 8),
            "ADD_TO_CART": (1, 3),
            "BUY": (0, 2),
        }
    },
    {
        "name": "Cluster 3: Văn Học / Nghệ Thuật",
        "preferred_slugs": ["van-hoc-tieu-thuyet"],
        "behavior": {
            "VIEW": (4, 12),
            "ADD_TO_CART": (0, 2),
            "BUY": (0, 1),
        }
    },
    {
        "name": "Cluster 4: Kỹ Năng / Tâm Lý",
        "preferred_slugs": ["ky-nang-song", "khoa-hoc-doi-song"],
        "behavior": {
            "VIEW": (3, 9),
            "ADD_TO_CART": (1, 4),
            "BUY": (0, 2),
        }
    },
]

INTERACTION_WEIGHTS = {
    "VIEW": 1.0,
    "ADD_TO_CART": 3.0,
    "BUY": 5.0,
}

DAYS_RANGE = 60  # Timestamp rải đều trong 60 ngày gần nhất


def random_timestamp_within_days(days: int) -> datetime:
    """Sinh timestamp ngẫu nhiên trong khoảng `days` ngày gần nhất."""
    now = datetime.now(timezone.utc)
    delta = timedelta(seconds=random.randint(0, days * 86400))
    return now - delta


def ensure_50_users(db) -> list[int]:
    """
    Đảm bảo hệ thống có đủ 50 khách hàng (ROLE_CUSTOMER) để huấn luyện ALS.
    Nếu thiếu, tự động tạo thêm các synthetic users và khởi tạo giỏ hàng rỗng.
    """
    rows = db.execute(
        text("SELECT id, username FROM users WHERE role = 'ROLE_CUSTOMER' ORDER BY id ASC")
    ).fetchall()
    existing_map = {r[1]: r[0] for r in rows}

    needed_total = 50
    now = datetime.now()
    dummy_password = "$2a$10$X8qYgG4jS3M3mZk1vJ8QEOt1D8y7.lM7g7vT4K3d1q1r1s1t1u1v1"

    new_users = []
    for i in range(1, needed_total + 1):
        username = f"synth_user_{i:02d}"
        if username not in existing_map and len(existing_map) + len(new_users) < needed_total:
            new_users.append({
                "username": username,
                "email": f"{username}@bookrunner.vn",
                "password": dummy_password,
                "full_name": f"Synthetic Reader {i:02d}",
                "phone": f"090{i:07d}",
                "address": "Việt Nam",
                "role": "ROLE_CUSTOMER",
                "enabled": 1,
                "token_version": 1,
                "refresh_token_jti": str(random.randint(100000, 999999)),
                "created_at": now,
                "updated_at": now,
            })

    if new_users:
        print(f"👥 Đang khởi tạo {len(new_users)} người dùng giả lập mẫu...")
        for u in new_users:
            res = db.execute(text("""
                INSERT INTO users (username, email, password, full_name, phone, address, role, enabled, token_version, refresh_token_jti, created_at, updated_at)
                VALUES (:username, :email, :password, :full_name, :phone, :address, :role, :enabled, :token_version, :refresh_token_jti, :created_at, :updated_at)
            """), u)
            user_id = res.lastrowid
            db.execute(text("INSERT INTO carts (user_id, updated_at) VALUES (:uid, :now)"), {"uid": user_id, "now": now})
        db.commit()

    all_customers = db.execute(
        text("SELECT id, username FROM users WHERE role = 'ROLE_CUSTOMER' ORDER BY id ASC")
    ).fetchall()
    return all_customers


def main():
    print("=" * 70)
    print("🌱 BOOKRUNNER SYNTHETIC DATA SEEDER — RecSys Training Pipeline")
    print("=" * 70)

    db = SessionLocal()
    try:
        # 1. Kiểm tra kết nối DB và tải danh mục, sách
        all_books = db.query(Book).filter(Book.active == True).all()
        if not all_books:
            print("❌ Không tìm thấy sách active nào trong DB!")
            print("   Vui lòng khởi động Spring Boot (book-runner) trước để DataInit tạo sách mẫu.")
            return

        categories = {c.id: c.slug for c in db.query(Category).all()}
        books_by_slug: dict[str, list] = {}
        for book in all_books:
            slug = categories.get(book.category_id, "unknown")
            if slug not in books_by_slug:
                books_by_slug[slug] = []
            books_by_slug[slug].append(book)

        print(f"\n📚 Tổng số sách active: {len(all_books)}")
        for slug, bks in books_by_slug.items():
            print(f"   - Thể loại [{slug}]: {len(bks)} cuốn")

        # 2. Đảm bảo đủ 50 users
        customer_rows = ensure_50_users(db)
        print(f"👥 Hệ thống hiện có {len(customer_rows)} khách hàng sẵn sàng.")

        # Phân bổ cố định theo 4 cụm Persona như RECSYS_DOCUMENTATION.md:
        # Cluster 1 (Tech): 15 users (ưu tiên customer01)
        # Cluster 2 (Business): 15 users (ưu tiên customer02)
        # Cluster 3 (Literature): 10 users (ưu tiên customer03)
        # Cluster 4 (Skills): 10 users (ưu tiên customer04)
        c1_users = []
        c2_users = []
        c3_users = []
        c4_users = []

        for uid, uname in customer_rows:
            if uname == "customer01":
                c1_users.append(uid)
            elif uname == "customer02":
                c2_users.append(uid)
            elif uname == "customer03":
                c3_users.append(uid)
            elif uname == "customer04":
                c4_users.append(uid)

        # Phân bổ các synthetic users còn lại
        assigned = set(c1_users + c2_users + c3_users + c4_users)
        remaining = [uid for uid, _ in customer_rows if uid not in assigned]

        for uid in remaining:
            if len(c1_users) < 15:
                c1_users.append(uid)
            elif len(c2_users) < 15:
                c2_users.append(uid)
            elif len(c3_users) < 10:
                c3_users.append(uid)
            elif len(c4_users) < 10:
                c4_users.append(uid)
            else:
                c1_users.append(uid)

        cluster_assignments = [
            (c1_users, PERSONA_CLUSTERS[0]),
            (c2_users, PERSONA_CLUSTERS[1]),
            (c3_users, PERSONA_CLUSTERS[2]),
            (c4_users, PERSONA_CLUSTERS[3]),
        ]

        print("\n📊 Phân bổ Cụm Persona:")
        for u_list, cluster in cluster_assignments:
            print(f"   - {cluster['name']}: {len(u_list)} users")

        if "--clean" in sys.argv:
            print("\n🧹 Xóa các tương tác cũ theo yêu cầu --clean...")
            db.execute(text("DELETE FROM user_book_interactions"))
            db.commit()

        # 4. Sinh interactions
        all_interactions = []
        print("\n⚙️ Đang sinh dữ liệu tương tác theo hành vi Persona...")

        for u_list, cluster in cluster_assignments:
            preferred_books = []
            for slug in cluster["preferred_slugs"]:
                preferred_books.extend(books_by_slug.get(slug, []))
            non_preferred_books = [b for b in all_books if b not in preferred_books]

            if not preferred_books:
                preferred_books = all_books

            for uid in u_list:
                # User tương tác với tất cả sách ưa thích (xác suất cao)
                # và 2-3 cuốn sách ngoài sở thích (khám phá ngẫu nhiên)
                sample_count = min(len(non_preferred_books), max(1, len(preferred_books)))
                target_books = preferred_books + random.sample(non_preferred_books, sample_count)

                for book in target_books:
                    is_pref = book in preferred_books

                    # VIEW interactions: Sách ưa thích xem nhiều lần (6-16 lượt), sách khác 1-3 lượt
                    view_range = (6, 16) if is_pref else (1, 3)
                    num_views = random.randint(*view_range)
                    for _ in range(num_views):
                        all_interactions.append({
                            "user_id": uid,
                            "book_id": book.id,
                            "interaction_type": "VIEW",
                            "weight": INTERACTION_WEIGHTS["VIEW"],
                            "explicit_rating": None,
                            "created_at": random_timestamp_within_days(DAYS_RANGE)
                        })

                    # ADD_TO_CART interactions
                    cart_prob = 0.75 if is_pref else 0.15
                    if random.random() < cart_prob:
                        cart_range = (2, 5) if is_pref else (1, 1)
                        num_carts = random.randint(*cart_range)
                        for _ in range(num_carts):
                            all_interactions.append({
                                "user_id": uid,
                                "book_id": book.id,
                                "interaction_type": "ADD_TO_CART",
                                "weight": INTERACTION_WEIGHTS["ADD_TO_CART"],
                                "explicit_rating": None,
                                "created_at": random_timestamp_within_days(DAYS_RANGE)
                            })

                    # BUY interactions
                    buy_prob = 0.60 if is_pref else 0.05
                    has_bought = False
                    if random.random() < buy_prob:
                        buy_range = (1, 3) if is_pref else (0, 1)
                        num_buys = random.randint(*buy_range)
                        for _ in range(num_buys):
                            has_bought = True
                            all_interactions.append({
                                "user_id": uid,
                                "book_id": book.id,
                                "interaction_type": "BUY",
                                "weight": INTERACTION_WEIGHTS["BUY"],
                                "explicit_rating": None,
                                "created_at": random_timestamp_within_days(DAYS_RANGE)
                            })

                    # RATING interactions (nếu đã mua, 70% cơ hội đánh giá 4-5 sao cho sách thích, 2-3 sao cho sách khác)
                    if has_bought and random.random() < 0.7:
                        rating_val = random.choice([4, 5]) if is_pref else random.choice([2, 3])
                        all_interactions.append({
                            "user_id": uid,
                            "book_id": book.id,
                            "interaction_type": "RATING",
                            "weight": float(rating_val),
                            "explicit_rating": rating_val,
                            "created_at": random_timestamp_within_days(DAYS_RANGE)
                        })

        print(f"📦 Đã tạo {len(all_interactions)} bản ghi tương tác giả lập trong bộ nhớ.")

        # 5. Bulk insert vào MariaDB
        print(f"💾 Đang ghi dữ liệu vào bảng 'user_book_interactions'...")
        chunk_size = 500
        for i in range(0, len(all_interactions), chunk_size):
            chunk = all_interactions[i:i + chunk_size]
            db.bulk_insert_mappings(UserBookInteraction, chunk)
            db.flush()
        db.commit()

        total_interactions = db.query(UserBookInteraction).count()
        print("\n" + "=" * 70)
        print(f"✅ THÀNH CÔNG! Đã nạp thành công {len(all_interactions)} tương tác.")
        print(f"   Tổng số tương tác hiện tại trong bảng: {total_interactions}")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ LỖI TRONG QUÁ TRÌNH SEED DỮ LIỆU: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
