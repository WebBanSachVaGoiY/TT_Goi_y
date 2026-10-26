"""
Script crawl toàn bộ ảnh bìa sách thật 100% từ Tiki Mobile API và tải về máy cục bộ.
- Lưu file ảnh vào Front_End/public/images/books/{id}.jpg và book-runner static
- Cập nhật cover_image_url = '/images/books/{id}.jpg'
- KHÔNG crawl review: đồng bộ chính xác theo bảng reviews hiện tại (sách nào chưa có review sẽ về 0.0 sao và 0 review).
"""
import sys
import os
import re
import json
import time
import shutil
import urllib.request
import urllib.parse
import pymysql

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_NAME = os.getenv("DB_NAME", "book_runner_db")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_IMG_DIR = os.path.join(BASE_DIR, "Front_End", "public", "images", "books")
BACKEND_IMG_DIR = os.path.join(BASE_DIR, "book-runner", "src", "main", "resources", "static", "images", "books")

HEADERS = {
    'User-Agent': 'Tiki/4.88.0 (iPhone; iOS 16.0; Scale/3.00)',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
}

def clean_search_term(title):
    # Bỏ nội dung trong ngoặc đơn: (The Alchemist), (Tập 1), etc.
    t = re.sub(r'\(.*?\)', '', title)
    # Cắt phụ đề sau dấu hai chấm hoặc gạch ngang dài
    t = t.split(':')[0].split('–')[0].split('-')[0]
    # Bỏ tiền tố "Sách", "Combo sách", "Giáo trình", "Bộ sách"
    t = re.sub(r'^(Sách|Combo\s*\d*\s*sách|Giáo trình|Bộ sách)\s*', '', t, flags=re.IGNORECASE)
    return t.strip()

def download_file(url, out_path):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=8) as resp:
        content = resp.read()
        if len(content) > 1000:
            with open(out_path, 'wb') as f:
                f.write(content)
            return len(content)
    return 0

def main():
    print("=" * 70, flush=True)
    print("   CRAWL ẢNH BÌA THẬT 100% TỪ TIKI VỀ LƯU CỤC BỘ (KHÔNG CRAWL REVIEW)", flush=True)
    print("=" * 70, flush=True)

    os.makedirs(FRONTEND_IMG_DIR, exist_ok=True)
    os.makedirs(BACKEND_IMG_DIR, exist_ok=True)

    conn = pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )
    cur = conn.cursor()

    cur.execute("SELECT id, title, author, isbn FROM books ORDER BY id ASC")
    books = cur.fetchall()
    print(f"\n📚 Tìm thấy {len(books)} cuốn sách trong database cần cập nhật ảnh bìa.", flush=True)

    success_img_count = 0

    print("\n>>> Bắt đầu tải ảnh bìa thật từ Tiki về máy...\n", flush=True)

    for idx, b in enumerate(books, 1):
        book_id = b["id"]
        title = b["title"]
        search_kw = clean_search_term(title)
        if len(search_kw) < 2:
            search_kw = title[:30]

        img_filename = f"{book_id}.jpg"
        fe_img_path = os.path.join(FRONTEND_IMG_DIR, img_filename)
        be_img_path = os.path.join(BACKEND_IMG_DIR, img_filename)

        already_has_valid_img = os.path.exists(fe_img_path) and os.path.getsize(fe_img_path) > 5000
        img_downloaded = already_has_valid_img

        if not already_has_valid_img:
            try:
                search_url = f"https://api.tiki.vn/v2/products?limit=1&q={urllib.parse.quote(search_kw)}"
                req = urllib.request.Request(search_url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read().decode())
                    items = data.get("data", [])
                    if items:
                        thumb_url = items[0].get("thumbnail_url")
                        if thumb_url:
                            size = download_file(thumb_url, fe_img_path)
                            if size > 1000:
                                shutil.copyfile(fe_img_path, be_img_path)
                                img_downloaded = True
                                success_img_count += 1
            except Exception as e:
                time.sleep(0.4)
        else:
            success_img_count += 1
            if not os.path.exists(be_img_path):
                shutil.copyfile(fe_img_path, be_img_path)

        # Cập nhật đường dẫn ảnh cục bộ vào database
        if img_downloaded or (os.path.exists(fe_img_path) and os.path.getsize(fe_img_path) > 1000):
            cur.execute("UPDATE books SET cover_image_url = %s WHERE id = %s", (f"/images/books/{img_filename}", book_id))

        # Đồng bộ sao và số lượt review theo đúng bảng reviews trong database (không fake số liệu)
        cur.execute("SELECT COUNT(*) as cnt, AVG(rating) as avg_r FROM reviews WHERE book_id = %s", (book_id,))
        stat = cur.fetchone()
        rev_count = stat["cnt"]
        avg_rating = round(float(stat["avg_r"]), 1) if stat["avg_r"] is not None else 0.0

        cur.execute(
            "UPDATE books SET average_rating = %s, total_reviews = %s WHERE id = %s",
            (avg_rating, rev_count, book_id)
        )

        status_icon = "🖼️ OK" if img_downloaded else "⚠️ MISS"
        print(f"[{idx:03d}/102] ID {book_id:3d}: {title[:32]:32} | {status_icon} | ⭐ {avg_rating:.1f} ({rev_count} reviews)", flush=True)

        time.sleep(0.15)

    conn.commit()

    # Thống kê kết quả
    cur.execute("SELECT count(*) as cnt FROM books WHERE cover_image_url LIKE '/images/books/%'")
    local_imgs_in_db = cur.fetchone()["cnt"]

    cur.execute("SELECT count(*) as cnt FROM books WHERE total_reviews > 0")
    books_with_reviews = cur.fetchone()["cnt"]

    print("\n" + "=" * 70, flush=True)
    print("🎉 HOÀN TẤT:", flush=True)
    print("=" * 70, flush=True)
    print(f"  + Số ảnh bìa thật đã tải về máy: {success_img_count}/{len(books)} cuốn", flush=True)
    print(f"  + Số sách trỏ vào đường dẫn cục bộ (/images/books/...): {local_imgs_in_db}/{len(books)}", flush=True)
    print(f"  + Số sách có review thật trong bảng 'reviews': {books_with_reviews}/{len(books)} cuốn", flush=True)
    print(f"  + Số sách chưa có review (hiển thị đúng 0.0 sao & 0 đánh giá): {len(books) - books_with_reviews}/{len(books)} cuốn", flush=True)
    print("=" * 70, flush=True)

    # Cập nhật snapshot offline JSON
    cur.execute("""
        SELECT b.id, b.title, b.author, b.publisher, b.publication_year, b.isbn,
               b.price, b.discount_price, b.stock_quantity, b.page_count, b.language,
               b.cover_image_url, b.average_rating, b.total_reviews, b.sold_count,
               b.is_featured, b.active, c.name as category_name, c.slug as category_slug,
               b.description
        FROM books b
        JOIN categories c ON b.category_id = c.id
        ORDER BY c.id, b.id
    """)
    all_books = cur.fetchall()
    for b in all_books:
        b['price'] = float(b['price'])
        b['discount_price'] = float(b['discount_price']) if b['discount_price'] is not None else None
        b['active'] = bool(b['active'])
        b['is_featured'] = bool(b['is_featured'])

    json_path = os.path.join(BASE_DIR, "TT_Goi_y", "data", "real_books_100.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_books, f, ensure_ascii=False, indent=2)
    print(f"💾 Đã cập nhật snapshot: {json_path}", flush=True)

    conn.close()

if __name__ == "__main__":
    main()
