from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """
    Tự động đọc từ file .env hoặc biến môi trường hệ thống.
    Các giá trị mặc định khớp với application.yaml của Spring Boot.
    """
    # --- Database Connection ---
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "book_runner_db"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""

    # --- RecSys Algorithm Hyperparameters ---
    # Content-Based Filtering
    CBF_TOP_K: int = 10             # Số sách tương tự ghi vào book_similarities
    CBF_MAX_FEATURES: int = 5000    # Số từ khóa TF-IDF tối đa
    CBF_SIMILARITY_TYPE: str = "CONTENT_BASED"

    # ALS Collaborative Filtering
    ALS_FACTORS: int = 32           # Số chiều ẩn K
    ALS_ITERATIONS: int = 15        # Số epoch huấn luyện
    ALS_REGULARIZATION: float = 0.1 # Hệ số chính quy hóa λ_reg
    ALS_ALPHA: float = 40.0         # Hệ số confidence: c_ui = 1 + alpha * R_ui
    ALS_TOP_K: int = 20             # Số sách gợi ý ghi vào user_recommendations

    # Time-Decay: w(e) = w_base * exp(-λ * Δt)
    # λ = 0.05 → chu kỳ bán rã ~14 ngày
    TIME_DECAY_LAMBDA: float = 0.05

    # Các hằng số nghiệp vụ — phải khớp với Java enum
    RECOMMENDATION_TYPE: str = "FOR_YOU"    # khớp với RecommendationType.FOR_YOU
    ALGORITHM_NAME: str = "ALS"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )


@lru_cache()
def get_settings() -> Settings:
    """Singleton settings — chỉ đọc file .env một lần."""
    return Settings()
