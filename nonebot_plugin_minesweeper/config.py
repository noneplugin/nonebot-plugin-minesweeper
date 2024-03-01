from nonebot import get_plugin_config
from pydantic import BaseModel, validator

from .utils import skin_list


class Config(BaseModel):
    minesweeper_default_skin: str = "winxp"

    @validator("minesweeper_default_skin")
    def validate_skin(cls, value: str) -> str:
        if value not in skin_list:
            raise ValueError(f"Skin {value} not found")
        return value


minesweeper_config = get_plugin_config(Config)
