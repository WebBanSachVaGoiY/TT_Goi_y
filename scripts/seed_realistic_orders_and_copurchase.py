"""
Script tạo dữ liệu đơn hàng mua chung thực tế (Multi-item Orders) cho các tài khoản
khách hàng trong MariaDB, sau đó kích hoạt tính toán thuật toán Co-Purchase (FBT)
để ghi vào bảng book_similarities (similarity_type='ALSO_BOUGHT').
"""
import sys
import os
import uuid
from datetime import datetime, timedelta
import random

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.book import Book, Category
from app.models.interaction import UserBookInteraction
from app.models.recommendation import BookSimilarity
from app.algorithms.co_purchase import run_co_purchase_training
from sqlalchemy import text


def seed_realistic_orders_and_copurchase():
    db = SessionLocal()
    try:
        print("🌱 [Seed] Bắt đầu nạp dữ liệu đơn hàng mua chung thực tế...")

        # 1. Lấy danh sách sách active theo từng danh mục
        books = db.query(Book).filter(Book.active == True).all()
        categories = db.query(Category).all()
        cat_map = {c.id: c.name for c in categories}
        books_by_cat = {}
        for b in books:
            cat_name = cat_map.get(b.category_id, "Khác")
            books_by_cat.setdefault(cat_name, []).append(b)

        print(f"📚 Đã tải {len(books)} sách thuộc {len(books_by_cat)} danh mục.")

        # Lấy các users khách hàng (customer01..customer04)
        user_rows = db.execute(text("SELECT id, username, full_name, phone, address FROM users WHERE role = 'ROLE_CUSTOMER'")).fetchall()
        if not user_rows:
            user_rows = db.execute(text("SELECT id, username, full_name, phone, address FROM users WHERE id > 1")).fetchall()
        if not user_rows:
            print("❌ Không tìm thấy user khách hàng nào trong DB!")
            return

        users = [
            {
                "id": r[0],
                "username": r[1],
                "name": r[2] or "Khách Hàng BookRunner",
                "phone": r[3] or "0901234567",
                "address": r[4] or "Số 123 Đường Sách, Q.1, TP.HCM"
            }
            for r in user_rows
        ]
        print(f"👥 Tìm thấy {len(users)} tài khoản khách hàng để tạo đơn hàng.")

        # 2. Xây dựng các nhóm sách thường được mua cùng nhau (Co-purchase bundles)
        # Ví dụ: Sách Lập trình đi cùng nhau; Sách Kinh tế đi cùng nhau; Sách Kỹ năng sống đi cùng nhau
        bundles = []

        # Bundles Lập trình & CNTT
        it_books = [b for b in books if "lập trình" in cat_map.get(b.category_id, "").lower() or "cntt" in cat_map.get(b.category_id, "").lower()]
        if len(it_books) >= 4:
            bundles.append([it_books[0].id, it_books[1].id])
            bundles.append([it_books[0].id, it_books[2].id, it_books[3].id])
            bundles.append([it_books[1].id, it_books[2].id])
            if len(it_books) >= 6:
                bundles.append([it_books[3].id, it_books[4].id, it_books[5].id])
                bundles.append([it_books[0].id, it_books[4].id])

        # Bundles Kinh tế & Khởi nghiệp
        econ_books = [b for b in books if "kinh tế" in cat_map.get(b.category_id, "").lower() or "khởi nghiệp" in cat_map.get(b.category_id, "").lower()]
        if len(econ_books) >= 4:
            bundles.append([econ_books[0].id, econ_books[1].id])
            bundles.append([econ_books[0].id, econ_books[2].id])
            bundles.append([econ_books[1].id, econ_books[2].id, econ_books[3].id])
            if len(econ_books) >= 6:
                bundles.append([econ_books[3].id, econ_books[4].id])
                bundles.append([econ_books[0].id, econ_books[5].id])

        # Bundles Kỹ năng sống & Tâm lý học
        skill_psy_books = [b for b in books if "kỹ năng" in cat_map.get(b.category_id, "").lower() or "tâm lý" in cat_map.get(b.category_id, "").lower()]
        if len(skill_psy_books) >= 4:
            bundles.append([skill_psy_books[0].id, skill_psy_books[1].id])
            bundles.append([skill_psy_books[1].id, skill_psy_books[2].id, skill_psy_books[3].id])
            bundles.append([skill_psy_books[0].id, skill_psy_books[2].id])
            if len(skill_psy_books) >= 6:
                bundles.append([skill_psy_books[4].id, skill_psy_books[5].id])

        # Bundles Văn học & Tiểu thuyết / Thiếu nhi
        lit_books = [b for b in books if "văn học" in cat_map.get(b.category_id, "").lower() or "tiểu thuyết" in cat_map.get(b.category_id, "").lower()]
        if len(lit_books) >= 4:
            bundles.append([lit_books[0].id, lit_books[1].id])
            bundles.append([lit_books[1].id, lit_books[2].id, lit_books[3].id])
            bundles.append([lit_books[0].id, lit_books[2].id])

        # Bundles Khoa học
        sci_books = [b for b in books if "khoa học" in cat_map.get(b.category_id, "").lower()]
        if len(sci_books) >= 3:
            bundles.append([sci_books[0].id, sci_books[1].id])
            bundles.append([sci_books[1].id, sci_books[2].id])

        print(f"📦 Đã thiết kế {len(bundles)} combo giỏ hàng mua chung tự nhiên.")

        # Xóa các đơn hàng test cũ nếu có mã 'ORD-REAL-'
        db.execute(text("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE order_code LIKE 'ORD-REAL-%')"))
        db.execute(text("DELETE FROM orders WHERE order_code LIKE 'ORD-REAL-%'"))
        db.commit()

        # Tạo đơn hàng trong DB
        created_orders = 0
        created_items = 0
        now = datetime.now()

        for idx, bundle_bids in enumerate(bundles):
            user = users[idx % len(users)]
            order_code = f"ORD-REAL-{idx+1:04d}"
            order_date = now - timedelta(days=random.randint(1, 15), hours=random.randint(1, 23))

            # Tính tổng tiền
            selected_books = [b for b in books if b.id in bundle_bids]
            total_amount = sum(float(b.price) for b in selected_books)
            shipping_fee = 20000.0
            final_amount = total_amount + shipping_fee

            # Tạo order
            order_res = db.execute(
                text("""
                    INSERT INTO orders (
                        order_code, user_id, recipient_name, recipient_phone,
                        shipping_address, total_amount, shipping_fee, final_amount,
                        payment_method, payment_status, status, note, created_at, updated_at
                    ) VALUES (
                        :code, :uid, :rname, :rphone, :addr, :total, :ship, :final,
                        'COD', 'PAID', 'DELIVERED', 'Đơn hàng trải nghiệm mua chung',
                        :cat, :uat
                    )
                """),
                {
                    "code": order_code,
                    "uid": user["id"],
                    "rname": user["name"],
                    "rphone": user["phone"],
                    "addr": user["address"],
                    "total": total_amount,
                    "ship": shipping_fee,
                    "final": final_amount,
                    "cat": order_date,
                    "uat": order_date
                }
            )
            order_id = order_res.lastrowid

            # Tạo order_items
            for b in selected_books:
                db.execute(
                    text("""
                        INSERT INTO order_items (order_id, book_id, price, quantity)
                        VALUES (:oid, :bid, :price, 1)
                    """),
                    {
                        "oid": order_id,
                        "bid": b.id,
                        "price": float(b.price)
                    }
                )
                created_items += 1

                # Tăng sold_count của sách
                db.execute(
                    text("UPDATE books SET sold_count = sold_count + 1 WHERE id = :bid"),
                    {"bid": b.id}
                )

                # Ghi nhận tương tác BUY vào user_book_interactions
                db.execute(
                    text("""
                        INSERT INTO user_book_interactions (user_id, book_id, interaction_type, weight, explicit_rating, created_at)
                        VALUES (:uid, :bid, 'BUY', 5.0, NULL, :cat)
                    """),
                    {
                        "uid": user["id"],
                        "bid": b.id,
                        "cat": order_date
                    }
                )

            created_orders += 1

        db.commit()
        print(f"✅ Đã tạo thành công {created_orders} đơn hàng thật với {created_items} sản phẩm và tương tác BUY.")

        # 3. Kích hoạt chạy thuật toán Co-Purchase
        print("\n⚙️ [CoPurchase] Kích hoạt thuật toán Co-Purchase FBT trên dữ liệu đơn hàng mới...")
        result = run_co_purchase_training(db)
        print(f"🎉 Kết quả huấn luyện Co-Purchase: {result}")

        # 4. Kiểm tra các cặp ALSO_BOUGHT trong DB
        similarities = db.query(BookSimilarity).filter(BookSimilarity.similarity_type == "ALSO_BOUGHT").all()
        print(f"\n📊 Tổng số cặp sách 'Thường được mua cùng' (ALSO_BOUGHT) trong DB: {len(similarities)}")

        # Hiển thị mẫu 10 cặp
        sample_rows = db.execute(text("""
            SELECT b1.id, b1.title, b2.id, b2.title, bs.score, bs.rank_order
            FROM book_similarities bs
            JOIN books b1 ON b1.id = bs.book_id_1
            JOIN books b2 ON b2.id = bs.book_id_2
            WHERE bs.similarity_type = 'ALSO_BOUGHT'
            ORDER BY bs.score DESC
            LIMIT 10
        """)).fetchall()

        print("\n📋 Top 10 cặp sách thường được mua cùng nhau:")
        for r in sample_rows:
            print(f"  • [{r[0]}] '{r[1][:30]}...'  <--->  [{r[2]}] '{r[3][:30]}...' | Score: {r[4]:.4f} (Rank {r[5]})")

    except Exception as e:
        db.rollback()
        print(f"❌ Lỗi khi seed dữ liệu đơn hàng và co-purchase: {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    seed_realistic_orders_and_copurchase()
