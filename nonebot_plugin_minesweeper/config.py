from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    minesweeper_default_skin: str = "winxp"


minesweeper_config = get_plugin_config(Config)
