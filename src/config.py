import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration."""
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")

    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    TIMEOUT_MS: int = int(os.getenv("TIMEOUT_MS", 30000))
    MAX_STATES: int = int(os.getenv("MAX_STATES", 1000))
    MAX_ELEMENTS_PER_STATE: int = 4
    MAX_SELECT_OPTIONS_PER_ELEMENT: int = 3
    
    PAGE_LOAD_STATE: str = os.getenv("PAGE_LOAD_STATE", "networkidle")

config = Config()
