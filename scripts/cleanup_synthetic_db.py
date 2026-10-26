"""
Script dọn dẹp toàn bộ dữ liệu giả lập (Synthetic Data) khỏi MariaDB:
- Xóa các đơn hàng ảo có mã 'ORD-SEED-%'
- Xóa các tương tác và giỏ hàng của tài khoản 'synth_user_%'
- Xóa tất cả các tài khoản ảo 'synth_user_%' khỏi bảng 'users'
- Đưa cơ sở dữ liệu về trạng thái chỉ có người dùng và đơn hàng THẬT.
"""
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal


def cleanup():
    print("=" * 70)
    print("🧹 BẮT ĐẦU DỌN DẸP DỮ LIỆU GIẢ LẬP KHỎI MARIADB (CLEANUP PIPELINE)...")
    print("=" * 70)

    db = SessionLocal()
    try:
        # 1. Dọn dẹp đơn hàng ảo (order_items và orders)
        old_orders = db.execute(text("SELECT id FROM orders WHERE order_code LIKE 'ORD-SEED-%'")).fetchall()
        if old_orders:
            order_ids = [str(r[0]) for r in old_orders]
            placeholders = ", ".join(order_ids)
            print(f"📦 Đang xóa {len(order_ids)} đơn hàng giả lập (ORD-SEED-*)...")
            db.execute(text(f"DELETE FROM order_items WHERE order_id IN ({placeholders})"))
            db.execute(text(f"DELETE FROM orders WHERE id IN ({placeholders})"))
            db.commit()
            print(f"   -> Đã xóa sạch đơn hàng và chi tiết đơn hàng mẫu.")
        else:
            print("📦 Không có đơn hàng giả lập nào trong bảng 'orders'.")

        # 2. Tìm danh sách user ảo synth_user_*
        synth_users = db.execute(text("SELECT id, username FROM users WHERE username LIKE 'synth_user_%'")).fetchall()
        if synth_users:
            user_ids = [str(r[0]) for r in synth_users]
            u_placeholders = ", ".join(user_ids)
            print(f"\n👥 Phát hiện {len(synth_users)} tài khoản ảo (synth_user_*)...")

            # Xóa user_book_interactions
            del_interactions = db.execute(text(f"DELETE FROM user_book_interactions WHERE user_id IN ({u_placeholders})")).rowcount
            print(f"   -> Đã xóa {del_interactions} tương tác của tài khoản ảo.")

            # Xóa user_recommendations
            del_recs = db.execute(text(f"DELETE FROM user_recommendations WHERE user_id IN ({u_placeholders})")).rowcount
            print(f"   -> Đã xóa {del_recs} gợi ý của tài khoản ảo.")

            # Xóa các cặp gợi ý ALSO_BOUGHT được tính từ đơn hàng ảo
            del_fbt = db.execute(text("DELETE FROM book_similarities WHERE similarity_type = 'ALSO_BOUGHT'")).rowcount
            print(f"   -> Đã xóa {del_fbt} gợi ý ALSO_BOUGHT trong book_similarities.")

            # Xóa carts và cart_items nếu có
            try:
                db.execute(text(f"""
                    DELETE ci FROM cart_items ci
                    JOIN carts c ON c.id = ci.cart_id
                    WHERE c.user_id IN ({u_placeholders})
                """))
                db.execute(text(f"DELETE FROM carts WHERE user_id IN ({u_placeholders})"))
                print(f"   -> Đã xóa giỏ hàng của tài khoản ảo.")
            except Exception as e:
                print(f"   (Bỏ qua xóa carts: {e})")

            # Xóa tài khoản trong bảng users
            del_users = db.execute(text(f"DELETE FROM users WHERE id IN ({u_placeholders})")).rowcount
            db.commit()
            print(f"   -> Đã xóa thành công {del_users} tài khoản ảo khỏi bảng 'users'.")
        else:
            print("\n👥 Bảng 'users' hoàn toàn sạch sẽ (không có tài khoản 'synth_user_*').")

        # Kiểm tra lại số lượng user và đơn hàng còn lại
        remaining_users = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
        remaining_orders = db.execute(text("SELECT COUNT(*) FROM orders")).scalar()

        print("\n" + "=" * 70)
        print("🎉 DỌN DẸP HOÀN TẤT! CƠ SỞ DỮ LIỆU ĐÃ SẠCH 100%:")
        print(f"   - Tổng số người dùng THẬT còn lại: {remaining_users}")
        print(f"   - Tổng số đơn hàng THẬT còn lại:    {remaining_orders}")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ LỖI TRONG QUÁ TRÌNH DỌN DẸP: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    cleanup()
