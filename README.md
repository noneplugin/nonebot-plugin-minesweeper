# nonebot-plugin-minesweeper

适用于 [Nonebot2](https://github.com/nonebot/nonebot2) 的 扫雷插件


### 安装

- 使用 nb-cli

```
nb plugin install nonebot_plugin_minesweeper
```

- 使用 pip

```
pip install nonebot_plugin_minesweeper
```


### 配置项

> 以下配置项可在 `.env.*` 文件中设置，具体参考 [NoneBot 配置方式](https://nonebot.dev/docs/appendices/config)

#### `minesweeper_default_skin`
 - 类型：`str`
 - 默认：`winxp`
 - 说明：扫雷默认皮肤


### 使用

**以下命令需要加[命令前缀](https://nonebot.dev/docs/appendices/config#command-start-和-command-separator) (默认为`/`)，可自行设置为空**

```
@机器人 + 扫雷 / minesweeper / 扫雷初级 / 扫雷中级 / 扫雷高级
```

*注：若命令前缀为空则需要 @机器人，否则可不@*

可使用 -r/--row ROWS 、-c/--col COLS 、-n/--num NUMS 自定义行列数和雷数；

可使用 -s/--skin SKIN 指定皮肤，默认为 winxp；

当前支持的皮肤：narkomania, mine, ocean, scratch, predator, clone, winxp, hibbeler, symbol, pacman, win98, winbw, maviz, colorsonly, icicle, mario, unknown, vista

使用 挖开/open/wk + 位置 来挖开方块，可同时指定多个位置；

使用 标记/mark/bj + 位置 来标记方块，可同时指定多个位置；

位置为 字母+数字 的组合，如“A1”


### 示例

<div align="left">
  <img src="https://s2.loli.net/2022/07/10/p1FYz5JoOwlcNXS.png" width="400" />
</div>


### 特别感谢

- [mzdluo123/MineSweeper](https://github.com/mzdluo123/MineSweeper) Mirai的扫雷小游戏
- [Minesweeper X](http://www.curtisbright.com/msx/) A minesweeper clone with extra features
