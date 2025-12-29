"""
Application configuration
"""
from pydantic_settings import BaseSettings
from typing import List


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
    MAX_GAMES_PER_REQUEST: int = 1000
    MAX_PROCESSING_TIME_SECONDS: int = 300  # 5 minutes
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 10
    
    # Mega-Sena Configuration
    MEGA_SENA_MIN_NUMBER: int = 1
    MEGA_SENA_MAX_NUMBER: int = 60
    MEGA_SENA_NUMBERS_PER_GAME: int = 6
    MEGA_SENA_GAME_PRICE: float = 5.00  # BRL (deprecated - use get_game_price function)
    
    @staticmethod
    def get_game_price(numbers_per_game: int) -> float:
        """Get Mega-Sena game price based on numbers per game"""
        prices = {
            6: 5.00,
            7: 35.00,
            8: 140.00,
            9: 420.00,
            10: 1050.00,
            11: 2310.00,
            12: 4620.00,
            13: 8580.00,
            14: 15015.00,
            15: 25025.00,
        }
        return prices.get(numbers_per_game, 5.00)
    
    # Historical Data
    HISTORICAL_DATA_URL: str = "https://asloterias.com.br/download-loterias/megasena"
    HISTORICAL_DATA_CACHE_TTL: int = 3600  # 1 hour
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

