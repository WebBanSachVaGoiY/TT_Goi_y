# 📘 TOÀN TẬP TÀI LIỆU KIẾN TRÚC & THUẬT TOÁN HỆ THỐNG GỢI Ý (RECSYS SPECIFICATION)

> **Dự án:** Hệ thống E-Commerce Bán Sách BookRunner (Spring Boot / Python FastAPI / React / MariaDB / Redis)  
> **Module:** Recommender System Microservice & Tracking Pipeline  
> **Cập nhật lần cuối:** 12/10/2026  
> **Trạng thái:** Hoàn thiện thiết kế kỹ thuật & Phân hệ Tracking; Sẵn sàng huấn luyện mô hình.

---

## 📑 MỤC LỤC
1. [Tổng Quan Bài Toán & Thách Thức](#1-tổng-quan-bài-toán--thách-thức)
2. [Kiến Trúc Vận Hành Tổng Thể (End-to-End Architecture)](#2-kiến-trúc-vận-hành-tổng-thể-end-to-end-architecture)
3. [Mô Hình Dữ Liệu & Các Bảng Database](#3-mô-hình-dữ-liệu--các-bảng-database)
4. [Phân Hệ Thu Thập & Tracking Hành Vi (Interaction Tracking)](#4-phân-hệ-thu-thập--tracking-hành-vi-interaction-tracking)
5. [Thuật Toán 1: Content-Based Filtering (Sách Tương Tự)](#5-thuật-toán-1-content-based-filtering-sách-tương-tự)
6. [Thuật Toán 2: Collaborative Filtering ALS với Implicit Feedback & Time-Decay](#6-thuật-toán-2-collaborative-filtering-als-với-implicit-feedback--time-decay)
7. [Chiến Lược Xử Lý Cold-Start (Người Dùng Mới & Sách Mới)](#7-chiến-lược-xử-lý-cold-start-người-dùng-mới--sách-mới)
8. [Kịch Bản Sinh Dữ Liệu Giả Lập (Synthetic Data Seeder)](#8-kịch-bản-sinh-dữ-liệu-giả-lập-synthetic-data-seeder)
9. [Chiến Lược Tích Hợp Redis Caching & Tối Ưu Tốc Độ](#9-chiến-lược-tích-hợp-redis-caching--tối-ưu-tốc-độ)
10. [Tầng Phục Vụ (Serving APIs) & Hiển Thị Giao Diện](#10-tầng-phục-vụ-serving-apis--hiển-thị-giao-diện)
11. [Đánh Giá Hiệu Năng Mô Hình (Evaluation Metrics)](#11-đánh-giá-hiệu-năng-mô-hình-evaluation-metrics)
12. [Đóng Gói Hệ Thống (DevOps & Docker Compose)](#12-đóng-gói-hệ-thống-devops--docker-compose)

---

> ### 📌 Trạng thái triển khai (cập nhật 2026)
> * ✅ **Đã triển khai trong mã nguồn:** §4 (Tracking), §5 (CBF), §6 (ALS), §7 (Cold-Start), §9 (Redis Cache + fallback RAM), §10 (Serving APIs — bao gồm cả co-purchase FBT `ALSO_BOUGHT`, endpoint trigger train, và nút "Huấn luyện lại gợi ý" trên trang Admin).
> * 🚧 **Chưa triển khai (TODO):** §11 (Evaluation Metrics — Precision@K/Recall@K/NDCG@K/Coverage) và §12 (Docker Compose đóng gói 5 dịch vụ).
>
> Bảng dưới đây mô tả **đặc tả thiết kế**; phần nào đã có code sẽ được ghi chú rõ.

---

## 1. TỔNG QUAN BÀI TOÁN & THÁCH THỨC

Trong một nền tảng thương mại điện tử bán sách trực tuyến, việc hiển thị danh sách sách tĩnh sẽ khiến khách hàng gặp khó khăn trong việc tìm kiếm tựa sách phù hợp. Hệ thống Recommender System (RecSys) đóng vai trò là "người bán hàng thông minh", cá nhân hóa trải nghiệm của từng độc giả.

### 1.1. Các Thách Thức Nghiệp Vụ Cốt Lõi
1. **Độ thưa thớt của dữ liệu (Data Sparsity - > 99.5%):**
   Một sàn sách có hàng ngàn tựa sách, nhưng mỗi khách hàng trung bình chỉ xem hoặc mua từ 3 đến 10 cuốn. Hầu hết các ô trong ma trận Người dùng – Sách đều là số 0.
2. **Tín hiệu phản hồi hỗn hợp (Implicit vs. Explicit Feedback):**
   * *Explicit (Tường minh):* Người dùng chấm điểm sao từ 1 đến 5 (chỉ chiếm $< 5\%$ người dùng).
   * *Implicit (Ngầm định):* Hành vi lướt xem (`VIEW`), thêm vào giỏ (`ADD_TO_CART`), đặt mua (`BUY`) chiếm $> 95\%$. Người dùng không chấm điểm, nhưng hành vi của họ phản ánh mức độ quan tâm thực tế.
3. **Bài toán Khởi đầu lạnh (Cold-Start Problem):**
   * *Cold-Start User:* Người dùng mới đăng ký tài khoản chưa có bất kỳ lịch sử xem hoặc mua sách nào.
   * *Cold-Start Item:* Cuốn sách mới nhập kho chưa từng có ai click xem hay đặt mua.
4. **Suy giảm sở thích theo thời gian (Concept Drift & Time-Decay):**
   Một cuốn sách khách hàng xem từ 3 tháng trước không phản ánh đúng nhu cầu hiện tại bằng một cuốn sách họ vừa thêm vào giỏ hàng ngày hôm qua.

### 1.2. Giải Pháp Tiếp Cận: Hybrid Recommender System
Hệ thống sử dụng mô hình kết hợp (Hybrid):
* **Content-Based Filtering (CBF):** Dựa trên đặc trưng nội dung văn bản (tiêu đề, tác giả, thể loại, mô tả). Giải quyết triệt để Cold-Start cho sách mới nhập kho.
* **Collaborative Filtering (CF - ALS):** Phân rã ma trận với phản hồi ngầm định (Implicit ALS) kết hợp hàm suy giảm thời gian (Time-Decay). Tạo danh sách gợi ý cá nhân hóa độc bản cho từng khách hàng.
* **Popularity & Quality Engine:** Đóng vai trò làm mạng lưới an toàn (Fallback) khi người dùng hoàn toàn chưa có dữ liệu.

---

## 2. KIẾN TRÚC VẬN HÀNH TỔNG THỂ (END-TO-END ARCHITECTURE)

```mermaid
flowchart TD
    subgraph ClientLayer ["1. CLIENT TƯƠNG TÁC (React Frontend)"]
        UI_Home["Trang Chủ: Gợi ý cho bạn"]
        UI_Detail["Chi tiết Sách: Sách tương tự"]
        UI_Action["Trigger: Xem sách / Thêm giỏ"]
    end

    subgraph TrackingLayer ["2. INTERACTION TRACKING & DATA COLLECTION"]
        UI_Action -->|POST /interactions/log| Ctrl["InteractionController (Spring Boot)"]
        Ctrl -->|Non-blocking @Async| Worker["Worker ThreadPool (CallerRunsPolicy)"]
        Worker -->|Atomic Debounce 15m/2m| CacheMap["In-Memory Cache (RAM)"]
        CacheMap -->|Hợp lệ| DB_Logs[("user_book_interactions<br/>(Composite Index)")]
    end

    subgraph MLEngine ["3. FASTAPI RECSYS MICROSERVICE (TT_Goi_y)"]
        DB_Catalog[("books & categories")] --> CBF_Engine["<b>Content-Based Engine</b><br/>• Tiền xử lý NLP<br/>• TF-IDF Vectorizer<br/>• Cosine Similarity"]
        CBF_Engine -->|Bulk Write Top-10| DB_Sim[("book_similarities")]

        DB_Logs --> ALS_Engine["<b>Collaborative Filtering Engine</b><br/>• Time-Decay: w * exp(-λΔt)<br/>• Bão hòa: R = 1 + ln(1+w)<br/>• Implicit Feedback ALS (k=32)<br/>• Phân rã User Factor & Item Factor"]
        ALS_Engine -->|Bulk Write Top-20| DB_Rec[("user_recommendations")]

        DB_Orders[("orders & order_items")] --> CoPurchase_Engine["<b>Co-Purchase Engine (FBT)</b><br/>• Dựng giỏ hàng theo đơn<br/>• Loại đơn CANCELLED/RETURNED<br/>• Top-K 2 chiều"]
        CoPurchase_Engine -->|Bulk Write Top-10 (ALSO_BOUGHT)| DB_Sim
    end

    subgraph ServingLayer ["4. SERVING & CACHING LAYER (Spring Boot)"]
        DB_Sim --> Svc_Related["getRelated(bookId)"]
        DB_Sim --> Svc_Fbt["getFrequentlyBoughtTogether(bookId)"]
        DB_Rec --> Svc_ForYou["getForYou(userId)"]
        ColdEngine["Cold-Start Engine<br/>(Top Bán chạy + Đánh giá cao)"] -.->|Fallback khi interactions < threshold| Svc_ForYou
        Catalog[("books.soldCount + averageRating")] -.->|Guest / Trending| Svc_Trending["getTrending()"]

        Svc_ForYou --> Redis[("REDIS CACHE<br/>for_you / related / fbt / trending")]
        Redis --> UI_Home
        Svc_Trending --> UI_Home
        Svc_Related --> UI_Detail
        Svc_Fbt --> UI_Detail
    end
```

---

## 3. MÔ HÌNH DỮ LIỆU & CÁC BẢNG DATABASE

Hệ thống RecSys tương tác trực tiếp với 3 bảng cốt lõi trong MariaDB (`book_runner_db`):

### 3.1. Bảng Sự Kiện Tương Tác: `user_book_interactions`
Lưu trữ toàn bộ các sự kiện thô (Raw Event Store) do người dùng phát sinh:
```sql
CREATE TABLE user_book_interactions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    book_id BIGINT NOT NULL,
    interaction_type VARCHAR(30) NOT NULL, -- 'VIEW', 'ADD_TO_CART', 'BUY', 'RATING'
    weight FLOAT NOT NULL,                 -- 1.0 (VIEW), 3.0 (ADD_TO_CART), 5.0 (BUY), 1.0-5.0 (RATING)
    explicit_rating INT NULL,              -- Điểm sao thực tế nếu là RATING
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ubi_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_ubi_book FOREIGN KEY (book_id) REFERENCES books(id),
    INDEX idx_user_book (user_id, book_id),
    INDEX idx_created_at (created_at),
    INDEX idx_user_book_type_created (user_id, book_id, interaction_type, created_at)
);
```

### 3.2. Bảng Tương Đồng Sách: `book_similarities`
Lưu trữ danh sách các cuốn sách tương đồng nhất do thuật toán Content-Based Filtering tính toán:
```sql
CREATE TABLE book_similarities (
    book_id_1 BIGINT NOT NULL,
    book_id_2 BIGINT NOT NULL,
    similarity_type VARCHAR(50) NOT NULL, -- 'CONTENT_BASED', 'ALSO_BOUGHT'
    score FLOAT NOT NULL,                 -- Điểm Cosine Similarity (0.0 đến 1.0)
    rank_order INT NOT NULL,              -- Thứ hạng: 1 đến 10
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (book_id_1, book_id_2, similarity_type),
    INDEX idx_book_similarity_lookup (book_id_1, similarity_type, rank_order)
);
```

### 3.3. Bảng Gợi Ý Cá Nhân Hóa: `user_recommendations`
Lưu trữ Top-20 cuốn sách gợi ý tốt nhất cho từng khách hàng do thuật toán ALS tính toán:
```sql
CREATE TABLE user_recommendations (
    user_id BIGINT NOT NULL,
    book_id BIGINT NOT NULL,
    recommendation_type VARCHAR(30) NOT NULL, -- 'FOR_YOU', 'DAILY_DISCOVER'
    algorithm VARCHAR(50) NOT NULL,           -- 'ALS', 'CONTENT_BASED', 'HYBRID'
    score FLOAT NOT NULL,                     -- Điểm dự đoán sở thích
    rank_order INT NOT NULL,                  -- Thứ hạng: 1 đến 20
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, book_id, recommendation_type),
    INDEX idx_user_type_rank (user_id, recommendation_type, rank_order)
);
```

---

## 4. PHÂN HỆ THU THẬP & TRACKING HÀNH VI (INTERACTION TRACKING)

Phân hệ Tracking đóng vai trò là "cảm biến" thu nạp tín hiệu ngầm. Phân hệ được thiết kế theo chuẩn Enterprise giải quyết triệt để 9 bài toán hệ thống:

```
[Browser Client] 
     │ (Chỉ gửi khi isAuthenticated === true)
     ▼
[InteractionController] ──► In-Memory Rate Limiter (Max 60 requests/phút/user)
     │
     ▼
[Worker ThreadPool] (Core: 4, Max: 8, Queue: 500, CallerRunsPolicy + UncaughtExceptionHandler)
     │
     ▼
[Atomic Debounce Cache] ──► ConcurrentHashMap.compute(key, ...)
     │                      • VIEW: TTL 15 phút
     │                      • ADD_TO_CART: TTL 2 phút
     │                      • Trùng trong TTL? ──► SKIP ngay tại RAM (0ms DB cost)
     ▼ (Hợp lệ)
[MariaDB] ──► INSERT INTO user_book_interactions (Composite Index tối ưu O(log N))
```

### Các Đặc Điểm Kỹ Thuật Đã Triển Khai:
1. **Triệt tiêu Race Condition trong Debounce:**
   Sử dụng hàm nguyên tử `ConcurrentHashMap.compute(cacheKey, ...)` khóa theo bucket trong RAM. Khi người dùng F5 nhanh hoặc hai request gửi tới cùng lúc, chỉ có request đầu tiên được cấp phát timestamp mới, request thứ hai bị loại bỏ ngay lập tức tại RAM ($0\text{ms}$).
2. **Xử lý Tinh tế Hành vi `ADD_TO_CART`:**
   Phía Frontend (`CartContext.jsx`), hệ thống kiểm tra `isAlreadyInCart`. Chỉ kích hoạt log `ADD_TO_CART` khi cuốn sách này là cuốn **mới thêm vào giỏ**. Nếu người dùng chỉ bấm nút cộng tăng số lượng cuốn sách đã có $\rightarrow$ Bỏ qua, tránh làm loãng trọng số.
3. **Chống React 18 StrictMode Double-Invoke:**
   Sử dụng `useRef(lastTrackedBookIdRef)` trong `BookDetailPage.jsx` đảm bảo trong môi trường phát triển (Development) mỗi lần xem sách chỉ gửi duy nhất 1 request `VIEW`.
4. **Bảo vệ Worker Pool:**
   Cấu hình `ThreadPoolTaskExecutor` có chặn trên (`maxPoolSize = 8`, `queueCapacity = 500`) và `CallerRunsPolicy` ngăn chặn sập server khi bị DDoS request.
5. **Chống Nuốt Lỗi (`AsyncUncaughtExceptionHandler`):**
   Mọi ngoại lệ trong tác vụ `@Async` đều được ghi log chi tiết phương thức, tham số và stack trace.

---

## 5. THUẬT TOÁN 1: CONTENT-BASED FILTERING (SÁCH TƯƠNG TỰ)

Thuật toán Content-Based Filtering tính toán mức độ tương đồng giữa các cuốn sách dựa trên nội dung mô tả của chúng.

```
┌──────────────┐     ┌──────────────┐     ┌────────────────┐     ┌────────────────────┐
│ Dữ liệu Sách │ ──► │ Tiền xử lý   │ ──► │ TF-IDF         │ ──► │ Cosine Similarity  │ ──► Top 10 Sách
│ (DB MariaDB) │     │ Nối Metadata │     │ Vectorizer     │     │ Ma trận Đối xứng   │     Tương tự
└──────────────┘     └──────────────┘     └────────────────┘     └────────────────────┘
```

### 5.1. Xây Dựng Hồ Sơ Sách (Item Profiling)
Chúng ta trích xuất và nối các trường thông tin của cuốn sách với trọng số tùy chỉnh:
$$\text{Document}_i = (\text{Title} \times 2) + (\text{Author} \times 2) + (\text{Category} \times 3) + \text{Description}$$
* Tiêu đề và tác giả được lặp lại 2 lần, thể loại lặp lại 3 lần để tăng độ nổi bật so với phần mô tả dài.

### 5.2. Trích Xuất Vector Đặc Trưng bằng TF-IDF
Sử dụng `TfidfVectorizer` từ `scikit-learn`:
* `ngram_range=(1, 2)`: Bắt cả từ đơn (*"lập trình"*) và cụm từ ghép (*"lập trình java"*, *"học máy"*).
* `max_features=5000`: Giữ lại 5.000 từ khóa mang tính phân biệt cao nhất.
* `stop_words`: Loại bỏ các từ dừng tiếng Việt phổ biến (*"là", "của", "và", "những", "các", "cuốn sách"*).

Giá trị TF-IDF của từ $t$ trong cuốn sách $d$:
$$\text{TF-IDF}(t, d) = \text{TF}(t, d) \times \left( \ln\left(\frac{1 + N}{1 + \text{DF}(t)}\right) + 1 \right)$$

### 5.3. Tính Toán Độ Tương Đồng Cosine (Cosine Similarity)
Với 2 vector đặc trưng $\vec{v}_i$ và $\vec{v}_j$ đại diện cho sách $i$ và sách $j$:
$$\text{Score}(i, j) = \cos(\vec{v}_i, \vec{v}_j) = \frac{\vec{v}_i \cdot \vec{v}_j}{\|\vec{v}_i\| \|\vec{v}_j\|} = \frac{\sum_{k=1}^M v_{i, k} \cdot v_{j, k}}{\sqrt{\sum_{k=1}^M v_{i, k}^2} \cdot \sqrt{\sum_{k=1}^M v_{j, k}^2}}$$
* Giá trị $\text{Score} \in [0, 1]$. Điểm càng gần 1, hai cuốn sách càng tương đồng về chủ đề.
* Với mỗi sách $i$, lấy Top 10 sách $j \ne i$ có score cao nhất và lưu vào `book_similarities`.

---

## 6. THUẬT TOÁN 2: COLLABORATIVE FILTERING ALS VỚI IMPLICIT FEEDBACK & TIME-DECAY

Đây là "trái tim" của hệ thống gợi ý, phân tích hành vi của đám đông để tìm ra các mẫu sở thích ngầm định mà người dùng chưa từng nhận ra.

```
Ma trận Tương tác R (User - Item)                 Phân rã Ma trận Tiềm ẩn (K = 32)
       Sách 1   Sách 2   Sách 3                           Factor 1  Factor 2
User 1 [ 4.2      0       1.5 ]         ≈       User 1 [   x11       x12   ]   ×   [ y11  y21  y31 ]
User 2 [  0      3.8       0  ]                 User 2 [   x21       x22   ]       [ y12  y22  y32 ]
User 3 [ 1.1     4.0      5.0 ]                 User 3 [   x31       x32   ]        (Ma trận Item Y)
                                                         (Ma trận User X)
```

### 6.1. Tổng Hợp Trọng Số & Hàm Suy Giảm Thời Gian (Time-Decay)
Từ các sự kiện trong `user_book_interactions`, mỗi sự kiện $e$ xảy ra cách thời điểm hiện tại $\Delta t$ ngày:
1. **Trọng số cơ sở (Base Weight $w_{\text{base}}$):**
   $$\text{VIEW} = 1.0, \quad \text{ADD\_TO\_CART} = 3.0, \quad \text{BUY} = 5.0, \quad \text{RATING} = \text{explicitRating}$$
2. **Công thức Suy giảm Thời gian (Time-Decay Exponential):**
   $$w(e) = w_{\text{base}}(e) \cdot e^{-\lambda \cdot \Delta t}$$
   * Hệ số suy giảm $\lambda = 0.05$ (chu kỳ bán rã khoảng 14 ngày).
   * Một cuốn sách xem 60 ngày trước chỉ còn trọng số $e^{-3} \approx 0.05$, nhường chỗ cho sở thích mới.
3. **Hàm Bão Hòa Logarit (Logarithmic Saturation):**
   $$R_{ui} = 1 + \ln\left(1 + \sum_{e \in E_{ui}} w(e)\right)$$
   * Nếu user tương tác vừa phải: $R_{ui}$ tăng đều.
   * Nếu user spam xem 50 lần: $R_{ui}$ tăng chậm theo hàm $\ln$, không phá vỡ cân bằng của mô hình.

### 6.2. Mô Hình Implicit ALS (Hu, Koren & Volinsky)
Trong phản hồi ngầm định, ta biến đổi giá trị $R_{ui}$ thành 2 đại lượng:
* **Sở thích nhị phân (Preference $p_{ui}$):**
  $$p_{ui} = \begin{cases} 1 & \text{nếu } R_{ui} > 0 \text{ (User có quan tâm đến sách)} \\ 0 & \text{nếu } R_{ui} = 0 \text{ (Chưa tương tác)} \end{cases}$$
* **Mức độ tự tin (Confidence $c_{ui}$):**
  $$c_{ui} = 1 + \alpha \cdot R_{ui} \quad (\text{chọn } \alpha = 40)$$
  * $R_{ui} = 0 \implies c_{ui} = 1$: Ta có mức tự tin tối thiểu rằng user không thích sách này.
  * $R_{ui} = 5.0 \implies c_{ui} = 201$: Ta cực kỳ tự tin rằng user thực sự yêu thích sách này.

### 6.3. Tối Ưu Hóa Bằng Thuật Toán ALS (Alternating Least Squares)
Mục tiêu là tìm ma trận vector người dùng $X \in \mathbb{R}^{U \times K}$ và ma trận vector sách $Y \in \mathbb{R}^{I \times K}$ ($K = 32$ chiều ẩn) để tối thiểu hóa hàm mất mát:
$$\mathcal{L} = \sum_{u=1}^U \sum_{i=1}^I c_{ui} \left( p_{ui} - \vec{x}_u^T \vec{y}_i \right)^2 + \lambda_{\text{reg}} \left( \sum_{u=1}^U \|\vec{x}_u\|^2 + \sum_{i=1}^I \|\vec{y}_i\|^2 \right)$$

Thuật toán giải bài toán qua các vòng lặp luân phiên (15 epochs):
1. **Cố định ma trận sách $Y$:** Giải nghiệm đóng cho từng vector người dùng $\vec{x}_u$:
   $$\vec{x}_u = \left( Y^T C^u Y + \lambda_{\text{reg}} I \right)^{-1} Y^T C^u p_u$$
2. **Cố định ma trận người dùng $X$:** Giải nghiệm đóng cho từng vector sách $\vec{y}_i$:
   $$\vec{y}_i = \left( X^T C^i X + \lambda_{\text{reg}} I \right)^{-1} X^T C^i p_i$$

### 6.4. Dự Đoán & Xếp Hạng (Ranking)
* Điểm dự đoán sở thích của user $u$ đối với sách $i$:
  $$\widehat{S}_{ui} = \vec{x}_u^T \vec{y}_i$$
* **Hậu xử lý:**
  1. Loại bỏ các cuốn sách người dùng **đã mua** (`BUY`).
  2. Sắp xếp các cuốn sách còn lại giảm dần theo điểm $\widehat{S}_{ui}$.
  3. Lấy Top 20 cuốn sách có điểm cao nhất ghi vào bảng `user_recommendations`.

---

## 7. CHIẾN LƯỢC XỬ LÝ COLD-START (NGƯỜI DÙNG MỚI & SÁCH MỚI)

```mermaid
flowchart TD
    UserReq["User yêu cầu gợi ý: GET /recommendations/for-you"] --> CheckCount{"Số tương tác của User >= app.recsys.user-cold-start-threshold?"}
    
    CheckCount -->|Có (Warm User)| ALS_Query["Query bảng user_recommendations<br/>(Do ALS tính toán)"]
    CheckCount -->|Không (Cold-Start User)| ColdEngine["Cold-Start Fallback Engine"]
    
    ColdEngine --> Strategy1["1. Top Sách Bán Chạy (soldCount DESC)"]
    ColdEngine --> Strategy2["2. Top Sách Đánh Giá Cao (averageRating >= 4.0)"]
    ColdEngine --> Combine["Hợp nhất & Trộn đều danh mục"]
    
    ALS_Query --> Return["Trả về Top 10 cuốn sách gợi ý"]
    Combine --> Return
```

1. **Đối với Người dùng mới (Cold-Start User):**
   * Ngưỡng phân loại: Người dùng có $< 5$ tương tác.
   * Chiến lược: Kết hợp Top sách bán chạy nhất (`BookRepository.findTopBestSellers`) và sách có rating cao nhất (`averageRating >= 4.0`).
   * Ngay khi người dùng lướt xem hoặc mua trên 5 cuốn sách $\rightarrow$ Ở chu kỳ train tiếp theo, hệ thống tự động chuyển tài khoản sang chế độ cá nhân hóa ALS.
2. **Đối với Sách mới nhập kho (Cold-Start Item):**
   * Được giải quyết triệt để nhờ thuật toán **Content-Based Filtering**: Sách mới chỉ cần có tiêu đề, tác giả và danh mục là lập tức tìm được danh sách sách tương tự để xuất hiện trên trang chi tiết sách mà không cần đợi lượt mua nào.

> ✅ **Đã triển khai** tại `RecommendationServiceImpl` (Spring Boot):
> * Cold-start user: đếm tương tác qua `UserBookInteractionRepository.countByUserId`; nếu `< app.recsys.user-cold-start-threshold` (mặc định 5) hoặc user chưa có gợi ý → gộp `findTrendingWithCategory` (soldCount) + `findTopRatedWithCategory` (averageRating ≥ 4.0) và loại trùng.
> * Khách vãng lai (`userId == null`) cũng dùng nhánh này (chính là endpoint `trending`).
> * Cold-start item: nếu `book_similarities` rỗng cho một sách, `getRelated` fallback sang các sách cùng danh mục (`findByCategoryExcludingWithCategory`).

---

## 8. KỊCH BẢN SINH DỮ LIỆU GIẢ LẬP (SYNTHETIC DATA SEEDER)

Để kiểm chứng thuật toán ALS và Content-Based hoạt động chuẩn xác trước khi ra mắt người dùng thật, script `scripts/seed_synthetic_data.py` sẽ nạp tập dữ liệu mô phỏng theo **4 cụm hành vi (Personas)**:

| Nhóm Sở Thích | Số Users | Thể Loại Ưa Thích (80% Tương Tác) | Hành Vi Mô Phỏng |
|:---|:---:|:---|:---|
| **Cluster 1: Developer / Tech** | 15 | Công nghệ thông tin, Lập trình, AI, DevOps | Xem và mua các sách Clean Code, Spring Boot, Python AI |
| **Cluster 2: Kinh Doanh / Tài Chính** | 15 | Kinh tế, Quản trị, Đầu tư, Khởi nghiệp | Xem và mua các sách Làm giàu, Chứng khoán, Marketing |
| **Cluster 3: Văn Học / Nghệ Thuật** | 10 | Tiểu thuyết, Văn học kinh điển, Truyện ngắn | Xem và mua các sách Trinh thám, Tác phẩm kinh điển |
| **Cluster 4: Kỹ Năng / Tâm Lý** | 10 | Tâm lý học, Kỹ năng sống, Phát triển bản thân | Xem và mua sách Đắc nhân tâm, Thao túng tâm lý... |

* **Quy mô nạp:** **50 người dùng mẫu**, **4.000 – 6.000 bản ghi tương tác**, timestamp rải đều trong **60 ngày gần nhất** để kiểm tra tính năng suy giảm thời gian Time-Decay.

> ⚠️ **Lưu ý về dữ liệu FBT:** `seed_synthetic_data.py` hiện chỉ sinh bảng `user_book_interactions` (phục vụ CBF/ALS). Thuật toán **Co-Purchase (FBT)** đọc từ `order_items JOIN orders`, nên trên một DB chỉ có dữ liệu seed thuần thì `/frequently-bought-together/{bookId}` sẽ trả rỗng cho tới khi có đơn hàng thật (hoặc seeder được mở rộng để sinh thêm `orders`/`order_items`).

---

## 9. CHIẾN LƯỢC TÍCH HỢP REDIS CACHING & TỐI ƯU TỐC ĐỘ

RecSys là phân hệ có tần suất đọc cực lớn (Read-heavy). Việc tích hợp Redis giúp giảm độ trễ từ **50ms** xuống **1-2ms**.

```
[Client Request] ──► [Spring Boot] ──► [Redis Cache (RAM)] ──► HIT (< 2ms) ──► Trả về Client
                                              │ (MISS)
                                              ▼
                                       [MariaDB Database] ──► Lưu Cache ──► Trả về Client
```

### 9.1. Các Khóa Cache (Cache Keys) & Thời Gian Sống (TTL)
1. **Gợi ý cá nhân hóa:** Key `recsys:for_you:{userId}` — TTL: **2 giờ** (`app.recsys.cache-ttl-hours`).
2. **Sách tương tự:** Key `recsys:related:{bookId}` — TTL: **12 giờ**.
3. **Thường được mua cùng (FBT):** Key `recsys:fbt:{bookId}` — TTL: **12 giờ**.
4. **Sách thịnh hành:** Key `recsys:trending` — TTL: **1 giờ**.
5. **Danh mục sách:** Key `catalog:categories:all` — TTL: **24 giờ**.

### 9.2. Cơ Chế Fallback An Toàn (Graceful Degradation)
Trong môi trường phát triển cục bộ (Local Dev), nếu máy tính chưa bật dịch vụ Redis trên cổng 6379, cấu hình Cache trong Spring Boot sẽ tự động fallback sang `ConcurrentMapCacheManager` (RAM nội bộ) hoặc truy vấn trực tiếp MariaDB mà **không bao giờ gây lỗi crash ứng dụng**.

> ✅ **Đã triển khai** tại `CacheConfig` (Spring Boot):
> * Khi khởi động, thử `ping()` Redis; nếu OK → `RedisCacheManager` với TTL riêng cho từng cache (`FOR_YOU` theo cấu hình, `RELATED`/`FBT` 12h, `TRENDING` 1h); nếu không → `ConcurrentMapCacheManager`.
> * `CacheErrorHandler` nuốt mọi lỗi cache runtime (chỉ log cảnh báo) → Redis chết giữa chừng cũng không làm hỏng request gợi ý.
> * Cần dependency `spring-boot-starter-cache` + `spring-boot-starter-data-redis` (đã thêm trong `build.gradle`).
> * Sau mỗi lần admin trigger train, `RecSysAdminServiceImpl` **xoá toàn bộ** 4 cache gợi ý để tránh dữ liệu cũ.

---

## 10. TẦNG PHỤC VỤ (SERVING APIS) & HIỂN THỊ GIAO DIỆN

### 10.1. Danh Sách Endpoint Phục Vụ Trong Spring Boot (`book-runner`)

> ✅ **Đã triển khai** tại `RecommendationController` (`/api/v1/recommendations`) và `AdminRecommendationController`.

| Endpoint | Phương thức | Phân quyền | Mô tả |
|:---|:---:|:---:|:---|
| `/api/v1/recommendations/for-you` | `GET` | `authenticated` | Top sách gợi ý cá nhân hóa (`?limit=`, mặc định 10, tối đa `app.recsys.max-recommendation-limit`). Có Cold-Start Fallback khi user ít tương tác hoặc chưa có dữ liệu ALS |
| `/api/v1/recommendations/related/{bookId}` | `GET` | `permitAll` | Top sách tương đồng nội dung (CBF). Fallback sang sách cùng danh mục khi chưa có dữ liệu mô hình |
| `/api/v1/recommendations/frequently-bought-together/{bookId}` | `GET` | `permitAll` | Top sách thường được mua cùng (Co-Purchase, `similarity_type = ALSO_BOUGHT`) |
| `/api/v1/recommendations/trending` | `GET` | `permitAll` | Sách bán chạy/nổi bật — dùng cho khách vãng lai (gộp `soldCount` + `averageRating ≥ 4.0`) |
| `/api/v1/admin/recommendations/train` | `POST` | `ROLE_ADMIN` | Trigger huấn luyện lại RecSys (`?type=all\|content-based\|collaborative\|co-purchase`), sau đó xoá cache gợi ý |

### 10.2. Danh Sách Endpoint Huấn Luyện Trong FastAPI (`TT_Goi_y`)

> ✅ **Đã triển khai** tại `app/api/recsys_router.py`.

| Endpoint | Phương thức | Mô tả |
|:---|:---:|:---|
| `/api/recsys/train/content-based` | `POST` | Huấn luyện TF-IDF & ghi đè bảng `book_similarities` |
| `/api/recsys/train/collaborative` | `POST` | Huấn luyện ALS & ghi đè bảng `user_recommendations` |
| `/api/recsys/train/co-purchase` | `POST` | Huấn luyện Co-Purchase (FBT) từ `order_items JOIN orders` & ghi `book_similarities` với type `ALSO_BOUGHT` |
| `/api/recsys/train/all` | `POST` | Chạy tuần tự cả 3 thuật toán trên (CBF → Co-Purchase → ALS) |
| `/api/recsys/health` | `GET` | Kiểm tra kết nối Database MariaDB và tình trạng Service |

Các endpoint **đọc** (debug/Swagger — Spring Boot vẫn là gateway chính cho Frontend):
`GET /api/recsys/users/{user_id}/recommendations`, `GET /api/recsys/books/{book_id}/similar`,
`GET /api/recsys/books/{book_id}/frequently-bought-together`, `GET /api/recsys/trending`.

---

## 11. ĐÁNH GIÁ HIỆU NĂNG MÔ HÌNH (EVALUATION METRICS)

> 🚧 **Chưa triển khai (TODO).** Phần dưới đây là đặc tả kế hoạch; chưa có script/hàm đánh giá nào trong mã nguồn hiện tại.

Để kiểm chứng chất lượng của mô hình gợi ý, hệ thống sử dụng các chỉ số đánh giá chuẩn khoa học dữ liệu:
1. **Precision@K ($K=10$):** Tỷ lệ các cuốn sách được gợi ý mà người dùng thực sự quan tâm trong tập kiểm thử (Test Set).
   $$\text{Precision@K} = \frac{|\text{Gợi ý} \cap \text{Đã mua/xem}|}{K}$$
2. **Recall@K ($K=10$):** Tỷ lệ các cuốn sách người dùng thích được hệ thống tìm ra thành công.
3. **NDCG@K (Normalized Discounted Cumulative Gain):** Đo lường chất lượng của thứ tự xếp hạng (sách người dùng thích nhất phải đứng ở vị trí top 1, 2 thay vì top 9, 10).
4. **Catalog Coverage:** Độ phủ của danh mục sách (đảm bảo hệ thống không chỉ gợi ý quanh quẩn vài cuốn sách nổi tiếng mà khai thác được cả các cuốn sách ở phần đuôi dài - Long Tail).

---

## 12. ĐÓNG GÓI HỆ THỐNG (DEVOPS & DOCKER COMPOSE)

> 🚧 **Chưa triển khai (TODO).** Chưa có `docker-compose.yml`/`Dockerfile` trong repo; phần dưới đây là kế hoạch đóng gói.

Toàn bộ hệ thống sẽ được đóng gói trong một file `docker-compose.yml` duy nhất khởi chạy 5 dịch vụ liên hoàn:
* **Service 1:** `mariadb:11` (Port 3306) — Lưu trữ dữ liệu quan hệ.
* **Service 2:** `redis:7-alpine` (Port 6379) — Bộ đệm Cache tốc độ cao.
* **Service 3:** `book-runner-app` (Port 8080) — Máy chủ Spring Boot Backend.
* **Service 4:** `fastapi-recsys` (Port 8000) — Máy chủ AI/RecSys Microservice.
* **Service 5:** `frontend-web` (Port 3000) — Ứng dụng React Vite.

---

*Tài liệu này là bản đặc tả kỹ thuật chính thức dùng làm kim chỉ nam xuyên suốt quá trình lập trình và nghiệm thu toàn bộ phân hệ Recommender System của dự án BookRunner.*
