import asyncio
import re
import shlex
from asyncio import TimerHandle
from dataclasses import dataclass, field
from io import BytesIO
from typing import Dict, List, NoReturn, Optional, Tuple

from nonebot import on_command, on_shell_command, require
from nonebot.adapters import Bot, Event, Message
from nonebot.exception import ParserExit
from nonebot.matcher import Matcher
from nonebot.params import CommandArg, CommandStart, EventToMe, ShellCommandArgv
from nonebot.plugin import PluginMetadata
from nonebot.rule import ArgumentParser

require("nonebot_plugin_saa")
require("nonebot_plugin_session")

from nonebot_plugin_saa import Image, MessageFactory
from nonebot_plugin_saa import __plugin_meta__ as saa_plugin_meta
from nonebot_plugin_session import SessionIdType
from nonebot_plugin_session import __plugin_meta__ as session_plugin_meta
from nonebot_plugin_session import extract_session

assert saa_plugin_meta.supported_adapters
assert session_plugin_meta.supported_adapters
supported_adapters = (
    saa_plugin_meta.supported_adapters & session_plugin_meta.supported_adapters
)

from .data_source import GameState, MarkResult, MineSweeper, OpenResult
from .utils import skin_list

__plugin_meta__ = PluginMetadata(
    name="扫雷",
    description="扫雷游戏",
    usage=(
        "@我 + 扫雷 开始游戏；\n"
        "@我 + 扫雷初级 / 扫雷中级 / 扫雷高级 可开始不同难度的游戏；\n"
        "可使用 -r/--row ROW 、-c/--col COL 、-n/--num NUM 自定义行列数和雷数；\n"
        "可使用 -s/--skin SKIN 指定皮肤，默认为 winxp；\n"
        "使用 挖开/open + 位置 来挖开方块，可同时指定多个位置；\n"
        "使用 标记/mark + 位置 来标记方块，可同时指定多个位置；\n"
        "位置为 字母+数字 的组合，如“A1”；\n"
        "发送 查看游戏 查看当前游戏状态；\n"
        "发送 结束 结束游戏；\n"
    ),
    type="application",
    homepage="https://github.com/noneplugin/nonebot-plugin-minesweeper",
    supported_adapters=supported_adapters,
    extra={
        "unique_name": "minesweeper",
        "example": "@小Q 扫雷\n挖开 A1\n标记 B2 C3",
        "author": "meetwq <meetwq@gmail.com>",
        "version": "0.3.0",
    },
)


parser = ArgumentParser("minesweeper", description="扫雷")
parser.add_argument("-r", "--row", type=int, default=8, help="行数")
parser.add_argument("-c", "--col", type=int, default=8, help="列数")
parser.add_argument("-n", "--num", type=int, default=10, help="雷数")
parser.add_argument("-s", "--skin", default="winxp", help="皮肤")
parser.add_argument("--show", action="store_true", help="显示游戏盘")
parser.add_argument("--stop", action="store_true", help="结束游戏")
parser.add_argument("--open", nargs="*", default=[], help="挖开方块")
parser.add_argument("--mark", nargs="*", default=[], help="标记方块")


@dataclass
class Options:
    row: int = 0
    col: int = 0
    num: int = 0
    skin: str = ""
    show: bool = False
    stop: bool = False
    open: List[str] = field(default_factory=list)
    mark: List[str] = field(default_factory=list)


games: Dict[str, MineSweeper] = {}
timers: Dict[str, TimerHandle] = {}

minesweeper = on_shell_command("minesweeper", parser=parser, block=True, priority=13)


@minesweeper.handle()
async def _(
    bot: Bot, matcher: Matcher, event: Event, argv: List[str] = ShellCommandArgv()
):
    await handle_minesweeper(bot, matcher, event, argv)


def get_cid(bot: Bot, event: Event):
    return extract_session(bot, event).get_id(SessionIdType.GROUP)


def game_running(bot: Bot, event: Event) -> bool:
    cid = get_cid(bot, event)
    return bool(games.get(cid, None))


# 命令前缀为空则需要to_me，否则不需要
def smart_to_me(command_start: str = CommandStart(), to_me: bool = EventToMe()) -> bool:
    return bool(command_start) or to_me


def shortcut(cmd: str, argv: List[str] = [], **kwargs):
    command = on_command(cmd, **kwargs, block=True, priority=12)

    @command.handle()
    async def _(
        bot: Bot,
        matcher: Matcher,
        event: Event,
        msg: Message = CommandArg(),
    ):
        try:
            args = shlex.split(msg.extract_plain_text().strip())
        except:
            args = []
        await handle_minesweeper(bot, matcher, event, argv + args)


shortcut("扫雷", ["--row", "8", "--col", "8", "--num", "10"], rule=smart_to_me)
shortcut("扫雷初级", ["--row", "8", "--col", "8", "--num", "10"], rule=smart_to_me)
shortcut("扫雷中级", ["--row", "16", "--col", "16", "--num", "40"], rule=smart_to_me)
shortcut("扫雷高级", ["--row", "16", "--col", "30", "--num", "99"], rule=smart_to_me)
shortcut("挖开", ["--open"], aliases={"open", "wk"}, rule=game_running)
shortcut("标记", ["--mark"], aliases={"mark", "bj"}, rule=game_running)
shortcut("查看游戏", ["--show"], aliases={"查看游戏盘", "显示游戏", "显示游戏盘"}, rule=game_running)
shortcut("结束", ["--stop"], aliases={"停", "停止游戏", "结束游戏"}, rule=game_running)


async def stop_game(matcher: Matcher, cid: str):
    timers.pop(cid, None)
    if games.get(cid, None):
        games.pop(cid)
        await matcher.finish("扫雷超时，游戏结束")


def set_timeout(matcher: Matcher, cid: str, timeout: float = 600):
    timer = timers.get(cid, None)
    if timer:
        timer.cancel()
    loop = asyncio.get_running_loop()
    timer = loop.call_later(
        timeout, lambda: asyncio.ensure_future(stop_game(matcher, cid))
    )
    timers[cid] = timer


async def handle_minesweeper(
    bot: Bot,
    matcher: Matcher,
    event: Event,
    argv: List[str],
):
    async def send(
        message: Optional[str] = None, image: Optional[BytesIO] = None
    ) -> NoReturn:
        if not (message or image):
            await matcher.finish()

        msg_builder = MessageFactory([])
        if message:
            if image:
                message += "\n"
            msg_builder.append(message)
        if image:
            msg_builder.append(Image(image))
        await msg_builder.send()
        await matcher.finish()

    try:
        args = parser.parse_args(argv)
    except ParserExit as e:
        if e.status == 0:
            await send(__plugin_meta__.usage)
        await send()

    help_msg = "使用 “挖开”+位置 挖开方块，使用 “标记”+位置 标记方块，可同时加多个位置，如：“挖开 A1 B2”"

    options = Options(**vars(args))

    cid = get_cid(bot, event)
    if not games.get(cid, None):
        if options.open or options.mark or options.show or options.stop:
            await send("没有正在进行的游戏")

        if options.row < 8 or options.row > 24:
            await send("行数应在8~24之间")

        if options.col < 8 or options.col > 30:
            await send("列数应在8~30之间")

        if options.num < 10 or options.num > options.row * options.col:
            await send("地雷数应不少于10且不多于行数*列数")

        if options.skin not in skin_list:
            await send("支持的皮肤：" + ", ".join(skin_list))

        game = MineSweeper(options.row, options.col, options.num, options.skin)
        games[cid] = game
        set_timeout(matcher, cid)

        await send(help_msg, game.draw())

    game = games[cid]
    set_timeout(matcher, cid)

    if options.show:
        await send(image=game.draw())

    if options.stop:
        games.pop(cid)
        await send("游戏已结束")

    open_positions = options.open
    mark_positions = options.mark
    if not (open_positions or mark_positions):
        await send(help_msg)

    def check_position(position: str) -> Optional[Tuple[int, int]]:
        match_obj = re.match(r"^([a-z])(\d+)$", position, re.IGNORECASE)
        if match_obj:
            x = (ord(match_obj.group(1).lower()) - ord("a")) % 32
            y = int(match_obj.group(2)) - 1
            return x, y

    msgs = []
    for position in open_positions:
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
            games.pop(cid)
            await send(msg, image=game.draw())
        elif res == OpenResult.OUT:
            msgs.append(f"位置 {position} 超出边界")
        elif res == OpenResult.DUP:
            msgs.append(f"位置 {position} 已经被挖过了")

    for position in mark_positions:
        pos = check_position(position)
        if not pos:
            msgs.append(f"位置 {position} 不合法，须为 字母+数字 的组合")
            continue
        res = game.mark(pos[0], pos[1])
        if res == MarkResult.WIN:
            games.pop(cid)
            await send("恭喜你获得游戏胜利！", image=game.draw())
        elif res == MarkResult.OUT:
            msgs.append(f"位置 {position} 超出边界")
        elif res == MarkResult.OPENED:
            msgs.append(f"位置 {position} 已经被挖开了，不能标记")

    await send("\n".join(msgs), image=game.draw())
