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
    MAX_ELEMENTS_PER_STATE: int = int(os.getenv("MAX_ELEMENTS_PER_STATE", 5))
    MAX_SELECT_OPTIONS_PER_ELEMENT: int = int(os.getenv("MAX_SELECT_OPTIONS_PER_ELEMENT", 3))

    MAX_ACTION_REPEATS_PER_URL: int = int(os.getenv("MAX_ACTION_REPEATS_PER_URL", 2))

    ACTION_RETRY_COUNT: int = int(os.getenv("ACTION_RETRY_COUNT", 2))
    REPLAY_RETRY_COUNT: int = int(os.getenv("REPLAY_RETRY_COUNT", 2))
    POPUP_TIMEOUT_MS: int = int(os.getenv("POPUP_TIMEOUT_MS", 3000))

    DOM_QUIET_MS: int = int(os.getenv("DOM_QUIET_MS", 400))
    DOM_SETTLE_TIMEOUT_MS: int = int(os.getenv("DOM_SETTLE_TIMEOUT_MS", 6000))
    USE_DOM_QUIESCENCE: bool = os.getenv("USE_DOM_QUIESCENCE", "true").lower() == "true"
    
    PAGE_LOAD_STATE: str = os.getenv("PAGE_LOAD_STATE", "networkidle")

    CLICK_NON_HTTP_LINKS: bool = os.getenv("CLICK_NON_HTTP_LINKS", "false").lower() == "true"

    DEFER_DESTRUCTIVE_ACTIONS: bool = os.getenv("DEFER_DESTRUCTIVE_ACTIONS", "true").lower() == "true"
    DESTRUCTIVE_KEYWORDS: str = os.getenv(
        "DESTRUCTIVE_KEYWORDS",
        "logout,log out,sign out,delete,remove,unsubscribe,cancel,checkout,pay,purchase,order,place order,reset,deactivate,terminate,drop,empty cart,clear cart",
    )

    LOGIN_USERNAME: str = os.getenv("LOGIN_USERNAME", "")
    LOGIN_PASSWORD: str = os.getenv("LOGIN_PASSWORD", "")

config = Config()
