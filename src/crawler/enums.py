from enum import StrEnum


class ActionType(StrEnum):
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    NAVIGATE = "navigate"
    PRESS = "press"


class HtmlTag(StrEnum):
    INPUT = "input"
    TEXTAREA = "textarea"
    SELECT = "select"
    BUTTON = "button"
    ANCHOR = "a"


class InputType(StrEnum):
    SUBMIT = "submit"
    BUTTON = "button"
    RESET = "reset"
    HIDDEN = "hidden"
    IMAGE = "image"
    FILE = "file"
    CHECKBOX = "checkbox"
    RADIO = "radio"
