from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_bool(key: str, default: str) -> bool:
    return str(os.getenv(key, default)).lower() == "true"


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return int(default)
    return int(raw)


@dataclass(slots=True)
class Config:
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str

    HEADLESS: bool
    TIMEOUT_MS: int
    MAX_STATES: int
    MAX_TRANSITIONS: int
    MAX_ELEMENTS_PER_STATE: int
    MAX_SELECT_OPTIONS_PER_ELEMENT: int
    MAX_ACTION_REPEATS_PER_URL: int

    ACTION_RETRY_COUNT: int
    REPLAY_RETRY_COUNT: int
    POPUP_TIMEOUT_MS: int

    DOM_QUIET_MS: int
    DOM_SETTLE_TIMEOUT_MS: int
    USE_DOM_QUIESCENCE: bool

    PAGE_LOAD_STATE: str

    CLICK_NON_HTTP_LINKS: bool

    DEFER_DESTRUCTIVE_ACTIONS: bool
    DESTRUCTIVE_KEYWORDS: str

    USE_SEMANTIC_DIVERSITY: bool
    SEMANTIC_DIVERSITY_THRESHOLD: float
    SEMANTIC_UNCERTAINTY_MARGIN: float
    SEMANTIC_MAX_BANK_SIZE: int
    SEMANTIC_ARTIFACT_DIR: str

    DATABASE_URL: str | None
    REDIS_URL: str | None
    ARQ_QUEUE_NAME: str
    ARQ_JOB_EXPIRES_MS: int
    CRAWLER_MAX_JOBS: int
    CRAWLER_JOB_TIMEOUT_SECONDS: int

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            NEO4J_URI=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            NEO4J_USER=os.getenv("NEO4J_USER", "neo4j"),
            NEO4J_PASSWORD=os.getenv("NEO4J_PASSWORD", "password"),
            HEADLESS=_env_bool("HEADLESS", "true"),
            TIMEOUT_MS=_env_int("TIMEOUT_MS", 3000),
            MAX_STATES=_env_int("MAX_STATES", 1000),
            MAX_TRANSITIONS=_env_int("MAX_TRANSITIONS", 5000),
            MAX_ELEMENTS_PER_STATE=_env_int("MAX_ELEMENTS_PER_STATE", 5),
            MAX_SELECT_OPTIONS_PER_ELEMENT=_env_int("MAX_SELECT_OPTIONS_PER_ELEMENT", 3),
            MAX_ACTION_REPEATS_PER_URL=_env_int("MAX_ACTION_REPEATS_PER_URL", 2),
            ACTION_RETRY_COUNT=_env_int("ACTION_RETRY_COUNT", 1),
            REPLAY_RETRY_COUNT=_env_int("REPLAY_RETRY_COUNT", 1),
            POPUP_TIMEOUT_MS=_env_int("POPUP_TIMEOUT_MS", 3000),
            DOM_QUIET_MS=_env_int("DOM_QUIET_MS", 400),
            DOM_SETTLE_TIMEOUT_MS=_env_int("DOM_SETTLE_TIMEOUT_MS", 3000),
            USE_DOM_QUIESCENCE=_env_bool("USE_DOM_QUIESCENCE", "true"),
            PAGE_LOAD_STATE=os.getenv("PAGE_LOAD_STATE", "networkidle"),
            CLICK_NON_HTTP_LINKS=_env_bool("CLICK_NON_HTTP_LINKS", "true"),
            DEFER_DESTRUCTIVE_ACTIONS=_env_bool("DEFER_DESTRUCTIVE_ACTIONS", "true"),
            DESTRUCTIVE_KEYWORDS=os.getenv(
                "DESTRUCTIVE_KEYWORDS",
                "logout,log out,sign out,delete,remove,unsubscribe,cancel,checkout,pay,purchase,order,place order,reset,deactivate,terminate,drop,empty cart,clear cart",
            ),
            SEMANTIC_DIVERSITY_THRESHOLD=float(os.getenv("SEMANTIC_DIVERSITY_THRESHOLD", "0.90")),
            SEMANTIC_UNCERTAINTY_MARGIN=float(os.getenv("SEMANTIC_UNCERTAINTY_MARGIN", "0.05")),
            SEMANTIC_MAX_BANK_SIZE=_env_int("SEMANTIC_MAX_BANK_SIZE", 1000),
            SEMANTIC_ARTIFACT_DIR=os.getenv(
                "SEMANTIC_ARTIFACT_DIR",
                os.path.join(os.path.dirname(__file__), "models", "semantic"),
            ),
            USE_SEMANTIC_DIVERSITY=_env_bool("USE_SEMANTIC_DIVERSITY", "true"),
            DATABASE_URL=os.getenv("DATABASE_URL") or None,
            REDIS_URL=os.getenv("REDIS_URL") or None,
            ARQ_QUEUE_NAME=os.getenv("CRAWL_ARQ_QUEUE_NAME", "arq:queue"),
            ARQ_JOB_EXPIRES_MS=_env_int("CRAWL_ARQ_EXPIRES_MS", 86400000),
            CRAWLER_MAX_JOBS=_env_int("CRAWLER_MAX_JOBS", 10),
            CRAWLER_JOB_TIMEOUT_SECONDS=_env_int("CRAWLER_JOB_TIMEOUT_SECONDS", 1800),
        )


config = Config.from_env()
