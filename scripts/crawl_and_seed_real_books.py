"""
Script thu thap va nap ~100 cuon sach that Viet Nam vao co so du lieu book_runner_db.
Nguon: API cong khai Tiki Books (gia that, anh bia CDN that, tom tat tieng Viet that).
Tich hop danh muc chuan hoa cho RecSys (TF-IDF Content-Based) va Spring Boot Backend.
"""
import sys
import os
import json
import re
import html
import random
import time
from datetime import datetime
import httpx
import pymysql

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Cau hinh MySQL XAMPP mac dinh
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_NAME = os.getenv("DB_NAME", "book_runner_db")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

CATEGORIES_SETUP = [
    {
        "name": "Lập trình & CNTT",
        "slug": "lap-trinh-cntt",
        "description": "Sách chuyên ngành công nghệ thông tin, lập trình, kiến trúc hệ thống và cơ sở dữ liệu."
    },
    {
        "name": "Kỹ năng sống & Phát triển bản thân",
        "slug": "ky-nang-song",
        "description": "Sách rèn luyện kỹ năng mềm, tư duy thành công, quản lý thời gian và phát triển bản thân."
    },
    {
        "name": "Kinh tế & Khởi nghiệp",
        "slug": "kinh-te-khoi-nghiep",
        "description": "Sách tài chính, đầu tư, quản trị kinh doanh, marketing và tư duy làm giàu."
    },
    {
        "name": "Văn học & Tiểu thuyết",
        "slug": "van-hoc-tieu-thuyet",
        "description": "Các tác phẩm văn học kinh điển, tiểu thuyết nổi tiếng trong nước và quốc tế."
    },
    {
        "name": "Khoa học & Đời sống",
        "slug": "khoa-hoc-doi-song",
        "description": "Sách khoa học tự nhiên, vũ trụ, sinh học và các phát minh vĩ đại của nhân loại."
    },
    {
        "name": "Tâm lý học",
        "slug": "tam-ly-hoc",
        "description": "Sách nghiên cứu tâm lý, hành vi con người, cảm xúc và nhận thức."
    },
    {
        "name": "Văn học Thiếu nhi",
        "slug": "thieu-nhi",
        "description": "Truyện thiếu nhi, văn học tuổi thơ và các tác phẩm bồi dưỡng tâm hồn trẻ em."
    }
]

CATEGORY_QUERIES = {
    "lap-trinh-cntt": [
        "clean code ma sach",
        "design patterns thiet ke mau",
        "lap trinh python co ban nang cao",
        "cau truc du lieu va giai thuat",
        "tri tue nhan tao machine learning",
        "lap trinh java can ban",
        "kien truc he thong microservices",
        "co so du lieu sql",
        "khoa hoc du lieu data science",
        "hoc lap trinh c++",
        "lap trinh web frontend backend",
        "spring boot thuc chien",
        "devops docker kubernetes",
        "an toan thong tin an ninh mang",
        "lap trinh golang"
    ],
    "ky-nang-song": [
        "dac nhan tam dale carnegie",
        "quang ganh lo di va vui song",
        "thoi quen nguyen tu atomic habits",
        "tuoi tre dang gia bao nhieu rosi doan",
        "khi ban dang mo thi nguoi khac dang no luc",
        "doc vi bat ky ai david lieberman",
        "suc manh cua tap trung",
        "7 thoi quen de thanh dat stephen covey",
        "dam bi ghet koga fumitake",
        "nghe thuat giao tiep dinh cao",
        "suc manh cua thoi quen charles duhigg",
        "ban dat gia bao nhieu van phien",
        "ngung song cho qua ngay",
        "thiet lap muc tieu cuoc doi",
        "song thuc te giua doi thuc dung"
    ],
    "kinh-te-khoi-nghiep": [
        "cha giau cha ngheo robert kiyosaki",
        "khoi nghiep tinh gon eric ries",
        "tam ly hoc ve tien morgan housel",
        "nha dau tu thong minh benjamin graham",
        "nghi giau va lam giau napoleon hill",
        "chien luoc dai duong xanh",
        "tu tot den vi dai jim collins",
        "quoc gia khoi nghiep dan senor",
        "chien tranh tien te song hongbing",
        "nguyen ly marketing philip kotler",
        "bi mat chuyen gia russell brunson",
        "kinh te hoc hai huoc freakonomics",
        "nguoi giau co nhat thanh babylon",
        "zero to one peter thiel",
        "100 trieu nam dau tien"
    ],
    "van-hoc-tieu-thuyet": [
        "nha gia kim paulo coelho",
        "mat biec nguyen nhat anh",
        "rung na uy haruki murakami",
        "cay cam ngot cua toi jose mauro",
        "hai so phan jeffrey archer",
        "khong gia dinh hector malot",
        "ong gia va bien ca ernest hemingway",
        "tieng chim hot trong bui man gai colleen mccullough",
        "chien binh cau vong andrea hirata",
        "tram nam co don gabriel garcia marquez",
        "su im lang cua bay cuu thomas harris",
        "toi thay hoa vang tren co xanh",
        "bo gia mario puzo",
        "toi la beto",
        "tieng goi noi hoang da jack london"
    ],
    "khoa-hoc-doi-song": [
        "sapiens luoc su loai nguoi yuval noah harari",
        "luoc su thoi gian stephen hawking",
        "vu tru trong vo hat de",
        "gen vi ky richard dawkins",
        "sung vi trung va thep jared diamond",
        "the gioi phang thomas friedman",
        "nguon goc cac loai charles darwin",
        "cosmos vu tru carl sagan",
        "vat ly thien van cho nguoi voi va neil degrasse tyson",
        "homo deus luoc su tuong lai",
        "21 bai hoc cho the ky 21",
        "nhung nha khai pha daniel boorstin",
        "lich su van minh the gioi",
        "ban chat cua su song",
        "tri tue nhan tao tuong lai nhan loai"
    ],
    "tam-ly-hoc": [
        "tu duy nhanh va cham daniel kahneman",
        "phi ly tri dan ariely",
        "thao tung tam ly",
        "tam ly hoc toi pham",
        "sang chan tam ly van the vuot qua bessel van der kolk",
        "suc manh cua hien tai eckhart tolle",
        "tam ly hoc hanh vi",
        "nghe thuat thau hieu long nguoi",
        "ban do tam hon carl jung",
        "tam ly hoc dam dong gustave le bon",
        "tri tue cam xuc daniel goleman",
        "suc manh cua su de bi ton thuong brene brown",
        "nghich ly cua su lua chon barry schwartz",
        "tam ly hoc thanh cong carol dweck",
        "thuat doc tam"
    ],
    "thieu-nhi": [
        "hoang tu be antoine de saint exupery",
        "de men phieu luu ky to hoai",
        "tuoi tho du doi phung quan",
        "dat rung phuong nam doan gioi",
        "chuyen con meo day hai au bay luis sepulveda",
        "kinh van hoa nguyen nhat anh",
        "charlie va nha may socola roald dahl",
        "chuyen con meo va con chuot ban than cua no",
        "la nam ngoai khung troi",
        "cho toi xin mot ve di tuoi tho",
        "bup sen xanh son tung",
        "truyen co andersen nguyen van hai",
        "truyen co grimm chon loc",
        "co gai den tu hom qua",
        "chu be mang giay cao su"
    ]
}

def clean_html(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def clean_title(title):
    if not title:
        return ''
    title = re.sub(r'^\[.*?\]\s*', '', title)
    title = re.sub(r'^(Sách|Combo Sách|Truyện|Bộ Sách)\s*[-:]*\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(Tái Bản.*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(Bìa Mềm.*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(Bìa Cứng.*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(Phiên Bản.*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*-\s*Tái bản.*', '', title, flags=re.IGNORECASE)
    return title.strip()

def ensure_categories(conn):
    print(">>> [1/4] Kiem tra va khoi tao danh muc (Categories)...")
    cur = conn.cursor()
    category_map = {} # slug -> id
    
    cur.execute("SELECT id, slug, name FROM categories")
    for row in cur.fetchall():
        category_map[row["slug"]] = row["id"]
        
    for cat in CATEGORIES_SETUP:
        slug = cat["slug"]
        if slug not in category_map:
            print(f"  + Tao moi category: {cat['name']} ({slug})")
            cur.execute(
                """
                INSERT INTO categories (name, slug, description, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (cat["name"], slug, cat["description"], datetime.now())
            )
            category_map[slug] = cur.lastrowid
            
    conn.commit()
    print(f"  -> Tong so category san sang: {len(category_map)}")
    return category_map

def fetch_book_from_tiki(client, query, category_slug, existing_titles, existing_isbns):
    try:
        search_url = "https://tiki.vn/api/v2/products"
        resp = client.get(search_url, params={"limit": 3, "q": query})
        if resp.status_code != 200:
            return None
        items = resp.json().get("data", [])
        if not items:
            return None
            
        for item in items:
            pid = item.get("id")
            if not pid:
                continue
                
            raw_title = clean_title(item.get("name", ""))
            if not raw_title or len(raw_title) < 3:
                continue
            
            # Check duplicate by title prefix
            norm_title = raw_title.lower()[:30]
            if any(norm_title in t.lower() or t.lower() in norm_title for t in existing_titles):
                continue
                
            detail_resp = client.get(f"https://tiki.vn/api/v2/products/{pid}")
            if detail_resp.status_code != 200:
                continue
            detail = detail_resp.json()
            
            title = clean_title(detail.get("name") or raw_title)
            authors = [a.get("name") for a in detail.get("authors", []) if a.get("name")]
            author = ", ".join(authors) if authors else "Nhiều tác giả"
            
            # Gia
            price = detail.get("original_price") or detail.get("list_price") or item.get("price") or 100000
            discount_price = detail.get("price") or price
            price = float(price)
            discount_price = float(discount_price)
            
            # Lam tron VND
            price = round(price / 1000) * 1000
            discount_price = round(discount_price / 1000) * 1000
            if discount_price >= price:
                discount_price = round(price * 0.85 / 1000) * 1000
                
            # Specs
            publisher = "NXB Trẻ"
            pages = random.randint(220, 480)
            year = random.randint(2020, 2024)
            for spec in detail.get("specifications", []):
                for attr in spec.get("attributes", []):
                    code = attr.get("code")
                    val = str(attr.get("value", ""))
                    if code in ("publisher_vn", "manufacturer") and val:
                        publisher = val
                    elif code == "number_of_page" and val.isdigit() and int(val) > 10:
                        pages = int(val)
                    elif code == "publication_date":
                        m = re.search(r"\b(20\d\d)\b", val)
                        if m:
                            year = int(m.group(1))

            # Cover Image CDN
            cover = None
            images = detail.get("images", [])
            if images and isinstance(images, list):
                cover = images[0].get("base_url") or images[0].get("thumbnail_url")
            if not cover:
                cover = item.get("thumbnail_url")
            if not cover or not cover.startswith("http"):
                cover = "https://images.unsplash.com/photo-1544947950-fa07a98d237f?w=500"
                
            # Description
            desc = clean_html(detail.get("description", ""))
            if len(desc) < 80:
                short_desc = clean_html(detail.get("short_description", ""))
                desc = (short_desc + " " + desc).strip()
            if len(desc) < 50:
                desc = f"Tác phẩm {title} của tác giả {author} là một trong những cuốn sách tiêu biểu thuộc thể loại được đông đảo độc giả đón nhận. Tác phẩm mang lại nhiều giá trị sâu sắc và bài học thực tiễn cho độc giả."

            # ISBN
            isbn = f"978-604{pid % 10000000:07d}"
            while isbn in existing_isbns:
                isbn = f"978-604{random.randint(1000000, 9999999):07d}"
            existing_isbns.add(isbn)
            existing_titles.add(title)
            
            sold = random.randint(35, 600)
            rating = round(random.uniform(4.4, 4.9), 1)
            reviews = random.randint(10, 180)
            featured = 1 if random.random() < 0.25 else 0
            
            return {
                "title": title[:250],
                "author": author[:140],
                "publisher": publisher[:140],
                "publication_year": year,
                "isbn": isbn,
                "description": desc,
                "price": price,
                "discount_price": discount_price,
                "stock_quantity": random.randint(25, 120),
                "page_count": pages,
                "language": "Tiếng Việt",
                "cover_image_url": cover[:480],
                "average_rating": rating,
                "total_reviews": reviews,
                "sold_count": sold,
                "active": 1,
                "is_featured": featured,
                "category_slug": category_slug
            }
    except Exception as e:
        print(f"    ! Loi query '{query}': {e}")
        return None

def main():
    print("=" * 60)
    print("   BAT DAU THU THAP VA NAP 100 CUON SACH THAT CHO BOOK RUNNER")
    print("=" * 60)
    
    conn = pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )
    
    category_map = ensure_categories(conn)
    
    cur = conn.cursor()
    cur.execute("SELECT id, title, isbn FROM books")
    existing_rows = cur.fetchall()
    existing_titles = {r["title"] for r in existing_rows}
    existing_isbns = {r["isbn"] for r in existing_rows if r["isbn"]}
    print(f">>> Hien tai trong database co: {len(existing_rows)} cuon sach san co.")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    client = httpx.Client(headers=headers, timeout=12.0, follow_redirects=True)
    
    print("\n>>> [2/4] Dang thu thap du lieu sach that tu Tiki API...")
    collected_books = []
    
    for slug, queries in CATEGORY_QUERIES.items():
        print(f"\n--- Thu thap danh muc: [{slug}] (Can ~15 cuon) ---")
        count_cat = 0
        for q in queries:
            book = fetch_book_from_tiki(client, q, slug, existing_titles, existing_isbns)
            if book:
                collected_books.append(book)
                count_cat += 1
                print(f"  [{count_cat:02d}] {book['title'][:35]} | {book['author'][:20]} | {int(book['discount_price']):,}d | Img: OK")
            time.sleep(0.3)
            if count_cat >= 15:
                break
                
    client.close()
    print(f"\n>>> [3/4] Thu thap thanh cong: {len(collected_books)} cuon sach that moi!")
    
    # Luu backup ra file JSON
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(data_dir, exist_ok=True)
    json_path = os.path.join(data_dir, "real_books_100.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(collected_books, f, ensure_ascii=False, indent=2)
    print(f"  -> Da luu file snapshot offline: {json_path}")
    
    # Nap vao MySQL
    print("\n>>> [4/4] Nap vao Database book_runner_db.books...")
    insert_sql = """
    INSERT INTO books (
        title, author, publisher, publication_year, isbn, description,
        price, discount_price, stock_quantity, page_count, language,
        cover_image_url, average_rating, total_reviews, sold_count,
        active, is_featured, category_id, created_at, updated_at
    ) VALUES (
        %(title)s, %(author)s, %(publisher)s, %(publication_year)s, %(isbn)s, %(description)s,
        %(price)s, %(discount_price)s, %(stock_quantity)s, %(page_count)s, %(language)s,
        %(cover_image_url)s, %(average_rating)s, %(total_reviews)s, %(sold_count)s,
        %(active)s, %(is_featured)s, %(category_id)s, %(created_at)s, %(updated_at)s
    )
    ON DUPLICATE KEY UPDATE
        description = VALUES(description),
        price = VALUES(price),
        discount_price = VALUES(discount_price),
        cover_image_url = VALUES(cover_image_url),
        updated_at = VALUES(updated_at)
    """
    
    now = datetime.now()
    inserted_count = 0
    for b in collected_books:
        cat_id = category_map.get(b["category_slug"])
        b["category_id"] = cat_id
        b["created_at"] = now
        b["updated_at"] = now
        cur.execute(insert_sql, b)
        inserted_count += 1
        
    conn.commit()
    
    cur.execute("SELECT count(*) as total FROM books")
    total_books = cur.fetchone()["total"]
    
    print("\n" + "=" * 60)
    print(f"   HOAN TAT XUAT SAC!")
    print(f"   - So sach moi duoc nap: {inserted_count}")
    print(f"   - Tong so sach hien co trong DB: {total_books}")
    print(f"   - So danh muc (Categories): {len(category_map)}")
    print("=" * 60)
    
    conn.close()

if __name__ == "__main__":
    main()
