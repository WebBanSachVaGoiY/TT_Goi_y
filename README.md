# 🤖 MICROSERVICE HỆ THỐNG GỢI Ý SÁCH (BOOKRUNNER RECSYS)

> **Công nghệ:** Python 3.13 / FastAPI / SQLAlchemy / Scikit-Learn / Implicit / MariaDB / Redis  
> **Tài liệu đặc tả toàn diện:** Xem tại [`RECSYS_DOCUMENTATION.md`](../RECSYS_DOCUMENTATION.md)

---

## 📌 TỔNG QUAN
Dự án Microservice phục vụ tính toán các thuật toán gợi ý sách:
1. **Content-Based Filtering:** Tính toán độ tương đồng giữa các cuốn sách dựa trên TF-IDF & Cosine Similarity từ Metadata (Tiêu đề, Tác giả, Danh mục, Mô tả). Ghi kết quả vào bảng `book_similarities`.
2. **Collaborative Filtering ALS:** Khai phá ma trận tương tác User-Item với phản hồi ngầm định (Implicit Feedback), kết hợp hàm suy giảm thời gian (Time-Decay: $w \cdot e^{-\lambda \Delta t}$). Ghi kết quả vào bảng `user_recommendations`.
3. **Synthetic Data Seeder:** Script sinh dữ liệu giả lập 50 users theo 4 cụm sở thích và 4.000+ tương tác phục vụ huấn luyện mô hình.

---

## 🛠️ CẤU TRÚC THƯ MỤC
```
TT_Goi_y/
├── app/
│   ├── main.py                     # Entry point FastAPI & API Docs
│   ├── config.py                   # Cấu hình kết nối DB & Tham số RecSys
│   ├── database.py                 # SQLAlchemy Engine & Session
│   ├── models/                     # SQLAlchemy Models (Book, Interaction, Recommendation)
│   ├── algorithms/                 # Thuật toán Content-Based & ALS
│   ├── services/                   # Training Service & ETL Pipeline
│   └── api/                        # REST API Router
├── scripts/
│   └── seed_synthetic_data.py      # Script sinh dữ liệu tương tác mẫu
├── requirements.txt
└── README.md
```

Chi tiết công thức toán học, luồng xử lý và kế hoạch triển khai xem tại file: [**`RECSYS_DOCUMENTATION.md`**](../RECSYS_DOCUMENTATION.md).
