from enum import Enum


class TestFlowType(str, Enum):
    MANUAL = "MANUAL"
    BUG_REPRODUCTION = "BUG_REPRODUCTION"
    COVERAGE = "COVERAGE"
