"""
Entry point chính của BookRunner RecSys Microservice.
Chạy bằng: uvicorn app.main:app --reload --port 8000
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.recsys_router import router as recsys_router

# Cấu hình logging toàn cục
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

app = FastAPI(
    title="BookRunner RecSys Microservice",
    description=(
        "Microservice AI tính toán gợi ý sách cho hệ thống E-Commerce BookRunner.\n\n"
        "**Thuật toán:**\n"
        "- **Content-Based Filtering**: TF-IDF Vectorizer + Cosine Similarity → bảng `book_similarities`\n"
        "- **Collaborative Filtering ALS**: Implicit Feedback + Time-Decay Exponential → bảng `user_recommendations`\n\n"
        "**Tích hợp:** Kết quả được ghi trực tiếp vào MariaDB `book_runner_db` "
        "và được Spring Boot phục vụ qua các endpoint `/api/v1/recommendations/**`."
    ),
    version="1.0.0",
    docs_url="/docs",       # Swagger UI
    redoc_url="/redoc"      # ReDoc UI
)

# CORS — cho phép Spring Boot (8080) và React dev server (3000/5173) gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký router
app.include_router(recsys_router)


@app.get("/", tags=["Root"], summary="Kiểm tra service online")
def root():
    """Endpoint root — xác nhận service đang chạy."""
    return {
        "service": "BookRunner RecSys Microservice",
        "status": "online",
        "swagger_docs": "http://localhost:8000/docs",
        "health_check": "http://localhost:8000/api/recsys/health",
    }
