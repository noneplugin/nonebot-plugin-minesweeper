import asyncio
import re
from asyncio import TimerHandle
from typing import Dict, Optional, Tuple

from nonebot import require
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.rule import to_me
from nonebot.utils import run_sync
from typing_extensions import Annotated

require("nonebot_plugin_alconna")
require("nonebot_plugin_session")

from nonebot_plugin_alconna import (
    Alconna,
    AlconnaQuery,
    Args,
    Image,
    MultiVar,
    Option,
    Query,
    Text,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_session import SessionId, SessionIdType

from .config import Config, minesweeper_config
from .data_source import GameState, MarkResult, MineSweeper, OpenResult
from .utils import skin_list

default_skin = minesweeper_config.minesweeper_default_skin

__plugin_meta__ = PluginMetadata(
    name="扫雷",
    description="扫雷游戏",
    usage=(
        "@我 + 扫雷 开始游戏；\n"
        "@我 + 扫雷初级 / 扫雷中级 / 扫雷高级 可开始不同难度的游戏；\n"
        "可使用 -r/--row ROW 、-c/--col COL 、-n/--num NUM 自定义行列数和雷数；\n"
        f"可使用 -s/--skin SKIN 指定皮肤，默认为 {default_skin}；\n"
        "使用 挖开/open + 位置 来挖开方块，可同时指定多个位置；\n"
        "使用 标记/mark + 位置 来标记方块，可同时指定多个位置；\n"
        "位置为 字母+数字 的组合，如“A1”；\n"
        "发送 查看游戏 查看当前游戏状态；\n"
        "发送 结束 结束游戏；\n"
    ),
    type="application",
    homepage="https://github.com/noneplugin/nonebot-plugin-minesweeper",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna", "nonebot_plugin_session"
    ),
    extra={
        "example": "@小Q 扫雷\n挖开 A1\n标记 B2 C3",
    },
)


games: Dict[str, MineSweeper] = {}
timers: Dict[str, TimerHandle] = {}


UserId = Annotated[str, SessionId(SessionIdType.GROUP)]


def game_is_running(user_id: UserId) -> bool:
    return user_id in games


def game_not_running(user_id: UserId) -> bool:
    return user_id not in games


minesweeper = on_alconna(
    Alconna(
        "minesweeper",
        Option("-r|--row", Args["rows", int], help_text="行数"),
        Option("-c|--col", Args["cols", int], help_text="列数"),
        Option("-n|--num", Args["nums", int], help_text="雷数"),
        Option("-s|--skin", Args["skin", str], help_text="皮肤"),
    ),
    aliases={"扫雷"},
    rule=to_me() & game_not_running,
    use_cmd_start=True,
    block=True,
    priority=13,
)
minesweeper.shortcut(
    "扫雷初级",
    {"prefix": True, "args": ["--row", "8", "--col", "8", "--num", "10"]},
)
minesweeper.shortcut(
    "扫雷中级",
    {"prefix": True, "args": ["--row", "16", "--col", "16", "--num", "40"]},
)
minesweeper.shortcut(
    "扫雷高级",
    {"prefix": True, "args": ["--row", "16", "--col", "30", "--num", "99"]},
)

minesweeper_show = on_alconna(
    "查看游戏",
    aliases={"查看游戏盘", "显示游戏", "显示游戏盘"},
    rule=game_is_running,
    use_cmd_start=True,
    block=True,
    priority=13,
)
minesweeper_stop = on_alconna(
    "结束",
    aliases={"结束游戏", "结束扫雷"},
    rule=game_is_running,
    use_cmd_start=True,
    block=True,
    priority=13,
)
minesweeper_open = on_alconna(
    Alconna("挖开", Args["open_positions", MultiVar(str, "+")]),
    aliases={"open", "wk"},
    rule=game_is_running,
    use_cmd_start=True,
    block=True,
    priority=13,
)
minesweeper_mark = on_alconna(
    Alconna("标记", Args["mark_positions", MultiVar(str, "+")]),
    aliases={"mark", "bj"},
    rule=game_is_running,
    use_cmd_start=True,
    block=True,
    priority=13,
)


def stop_game(user_id: str):
    if timer := timers.pop(user_id, None):
        timer.cancel()
    games.pop(user_id, None)


async def stop_game_timeout(matcher: Matcher, user_id: str):
    game = games.get(user_id, None)
    stop_game(user_id)
    if game:
        await matcher.send("扫雷超时，游戏结束")


def set_timeout(matcher: Matcher, user_id: str, timeout: float = 300):
    if timer := timers.get(user_id, None):
        timer.cancel()
    loop = asyncio.get_running_loop()
    timer = loop.call_later(
        timeout, lambda: asyncio.ensure_future(stop_game_timeout(matcher, user_id))
    )
    timers[user_id] = timer


@minesweeper.handle()
async def _(
    matcher: Matcher,
    user_id: UserId,
    rows: Query[int] = AlconnaQuery("rows", 8),
    cols: Query[int] = AlconnaQuery("cols", 8),
    nums: Query[int] = AlconnaQuery("nums", 10),
    skin: Query[str] = AlconnaQuery("skin", default_skin),
):
    if rows.result < 8 or rows.result > 24:
        await matcher.finish("行数应在8~24之间")

    if cols.result < 8 or cols.result > 30:
        await matcher.finish("列数应在8~30之间")

    if nums.result < 10 or nums.result > rows.result * cols.result:
        await matcher.finish("地雷数应不少于10且不多于行数*列数")

    if skin.result not in skin_list:
        await matcher.finish("支持的皮肤：" + ", ".join(skin_list))

    game = MineSweeper(rows.result, cols.result, nums.result, skin.result)
    games[user_id] = game
    set_timeout(matcher, user_id)

    msg = Text(
        "使用 “挖开”+位置 挖开方块，使用 “标记”+位置 标记方块，"
        "可同时加多个位置，如：“挖开 A1 B2”"
    ) + Image(raw=await run_sync(game.draw)())
    await msg.send()


@minesweeper_show.handle()
async def _(matcher: Matcher, user_id: UserId):
    game = games[user_id]
    set_timeout(matcher, user_id)

    await UniMessage.image(raw=await run_sync(game.draw)()).send()


@minesweeper_stop.handle()
async def _(matcher: Matcher, user_id: UserId):
    stop_game(user_id)
    await matcher.finish("游戏已结束")


def check_position(position: str) -> Optional[Tuple[int, int]]:
    match_obj = re.match(r"^([a-z])(\d+)$", position, re.IGNORECASE)
    if match_obj:
        x = (ord(match_obj.group(1).lower()) - ord("a")) % 32
        y = int(match_obj.group(2)) - 1
        return x, y


@minesweeper_open.handle()
async def _(
    matcher: Matcher,
    user_id: UserId,
    open_positions: Query[Tuple[str, ...]] = AlconnaQuery("open_positions", ()),
):
    game = games[user_id]
    set_timeout(matcher, user_id)

    msgs = []
    for position in open_positions.result:
        pos = check_position(position)
        if not pos:
            msgs.append(f"位置 {position} 不合法，须为 字母+数字 的组合")
            continue
        res = game.open(pos[0], pos[1])
        if res in [OpenResult.WIN, OpenResult.FAIL]:
            msg = ""
            if game.state == GameState.WIN:
                msg = "恭喜你获得游戏胜利！"
            elif game.state == GameState.FAIL:
                msg = "很遗憾，游戏失败"
            stop_game(user_id)
            await (Text(msg) + Image(raw=await run_sync(game.draw)())).send()
            await matcher.finish()

        elif res == OpenResult.OUT:
            msgs.append(f"位置 {position} 超出边界")

        elif res == OpenResult.DUP:
            msgs.append(f"位置 {position} 已经被挖过了")

    await (Text("\n".join(msgs)) + Image(raw=await run_sync(game.draw)())).send()


@minesweeper_mark.handle()
async def _(
    matcher: Matcher,
    user_id: UserId,
    mark_positions: Query[Tuple[str, ...]] = AlconnaQuery("mark_positions", ()),
):
    game = games[user_id]
    set_timeout(matcher, user_id)

    msgs = []
    for position in mark_positions.result:
        pos = check_position(position)
        if not pos:
            msgs.append(f"位置 {position} 不合法，须为 字母+数字 的组合")
            continue
        res = game.mark(pos[0], pos[1])
        if res == MarkResult.WIN:
            msg = "恭喜你获得游戏胜利！"
            stop_game(user_id)
            await (Text(msg) + Image(raw=await run_sync(game.draw)())).send()
            await matcher.finish()

        elif res == MarkResult.OUT:
            msgs.append(f"位置 {position} 超出边界")

        elif res == MarkResult.OPENED:
            msgs.append(f"位置 {position} 已经被挖开了，不能标记")

    await (Text("\n".join(msgs)) + Image(raw=await run_sync(game.draw)())).send()
