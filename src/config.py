import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration."""

    PG_HOST: str = os.getenv("PG_HOST", "localhost")
    PG_PORT: int = int(os.getenv("PG_PORT", 5432))
    PG_USER: str = os.getenv("PG_USER", "postgres")
    PG_PASSWORD: str = os.getenv("PG_PASSWORD", "postgres")
    PG_DATABASE: str = os.getenv("PG_DATABASE", "coverit_crawler")

    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")

    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    TIMEOUT_MS: int = int(os.getenv("TIMEOUT_MS", 30000))
    MAX_STATES: int = int(os.getenv("MAX_STATES", 1000))

    @property
    def pg_connection_string(self) -> str:
        return f"postgresql+asyncpg://{self.PG_USER}:{self.PG_PASSWORD}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DATABASE}"


config = Config()
