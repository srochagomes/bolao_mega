"""
Application configuration
"""
from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # API Configuration
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    # Job Processing
    MAX_CONCURRENT_JOBS: int = 3
    JOB_TTL_SECONDS: int = 1800  # 30 minutes
    MAX_GAMES_PER_REQUEST: int = 10_000_000  # 10 milhões de jogos (usando streaming)
    MAX_PROCESSING_TIME_SECONDS: int = 3600  # 60 minutes (aumentado para grandes volumes)
    
    # Ray Configuration
    USE_RAY: bool = True  # Use Ray for distributed processing if available
    RAY_MIN_QUANTITY: int = 10  # Use Ray for quantities >= this value (reduced for better performance)
    RAY_NUM_WORKERS: Optional[int] = None  # None = use all available CPUs
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 10
    
    # Mega-Sena Configuration
    MEGA_SENA_MIN_NUMBER: int = 1
    MEGA_SENA_MAX_NUMBER: int = 60
    MEGA_SENA_NUMBERS_PER_GAME: int = 6
    MEGA_SENA_GAME_PRICE: float = 6.00  # BRL (deprecated - use get_game_price function)
    
    @staticmethod
    def get_game_price(numbers_per_game: int) -> float:
        """Get Mega-Sena game price based on numbers per game"""
        prices = {
            6: 6.00,
            7: 42.00,
            8: 168.00,
            9: 504.00,
            10: 1260.00,
            11: 2772.00,
            12: 5544.00,
            13: 10296.00,
            14: 18018.00,
            15: 30030.00,
            16: 48048.00,
            17: 74256.00,
        }
        return prices.get(numbers_per_game, 6.00)
    
    # Historical Data
    HISTORICAL_DATA_URL: str = "https://asloterias.com.br/download-loterias/megasena"
    HISTORICAL_DATA_CACHE_TTL: int = 3600  # 1 hour
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

