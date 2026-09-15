# -*- coding: utf-8 -*-
"""
================================================================================
《一箭又一箭》 —— 点击解谜小游戏（Python 3 + Pygame）
================================================================================

【核心玩法】
    棋盘上的每个箭头都是**有长度、内部还能拐弯**的一条折线（箭尾 -> 箭头）。
    点击一个箭头：
        1. 看它**箭头前方**那条射线上有没有别的箭头；
        2. 没有阻挡  ->  **本体**沿着自己的轨道飞出棋盘并消失；
        3. 有阻挡    ->  **本体**先沿轨道冲过去撞在被挡的那一格上，再阻尼弹回原位，
                        被撞的格子标红、接触点闪白光，同时失误次数 -1；
        4. 清空本关所有箭头 = 通关；失误次数用完 = 失败。
    注意：悬停**不会**告诉你哪支箭能飞（早先的红/绿预览框已经去掉），
    能不能走要自己看盘面判断 —— 否则只要看颜色就行了，谜题就不成立。

【三种玩法】
    · 关卡模式   3 个手写/生成的关卡，逐关推进；全部通关后解锁无尽模式
    · 无尽模式   随机关卡，一关比一关大；**失败即整局结束**，成绩写进最佳记录
    · 速度模式   60 秒内尽可能多地通过机关；每失误一次扣 3 秒
    最佳记录存在脚本旁边的 save.json 里，首页显示。

【箭是怎么动的：沿轨道走，不是整体刚性平移】
    轨道 = [箭身自己的格子] + [箭头前方延长出去的格子]
    前进 offset 格 = 把箭身放到轨道上 offset ~ offset+length-1 这一段。
    于是头部先沿着朝向直行，后面的拐弯一点点被"拉直"（像火车沿铁轨开出去）；
    **每一步只有箭头那一格会进入新格子**，所以判定只需要看"箭头正前方有没有别的箭"。
    动画只改 Arrow.offset，画出来的始终是同一个箭头对象，不会出现
    "本体留在原地 + 幻影飞出去"。

【棋盘数据结构：单元格邻居图】
    · 每个被占用的格子是一个 CellNode，记录它四个方向上最近的邻居；
    · 每个格子都指向它所属的 Arrow（不需要靠坐标反查归属）；
    · "箭头正前方有没有别的箭" = 从箭头格沿邻居链跳过自己的箭身，看第一个
      "别人家的"格子是不是 None —— 常数级；
    · 一支箭飞出后，把它所有格子逐个拆链（上下对接、左右对接）即可。
    整张图由 Board.rebuild_neighbors() 从箭头数据列表一次性建好。

【关卡数据格式】
    {"name": ..., "rows": 6, "cols": 6, "max_mistakes": 3,
     "arrows": [arrow(行, 列, 长度, 方向),    # 直线箭头
                poly([(3,3), (3,4), (4,4)]),  # 带拐弯的箭头（从箭尾走到箭头）
                ...]}

【本文件包含的三大扩展点】（搜索这些字样即可定位）
    # === 后续在此处添加箭头点击与路径检测逻辑 ===
    # === 后续在此处添加飞出与碰撞动画反馈逻辑 ===
    # === 后续在此处添加关卡数据与切换逻辑 ===

【运行方式】
    python arrow_puzzle.py                # 从第 1 关开始
    python arrow_puzzle.py --level 2      # 直接从第 3 关开始（下标从 0 起）
    python arrow_puzzle.py --endless      # 直接进无尽模式
    python arrow_puzzle.py --speed        # 直接进速度模式
    python arrow_puzzle.py --selftest     # 无窗口自检（15 项）
    游戏中按 D 可切换"邻居图可视化"。

【依赖】
    pygame（vendor/ 里内置了兼容 Python 3.7 的 pygame 2.1.2，自动加载）。
================================================================================
"""

import array
import hashlib
import json
import math
import os
import random
import shutil
import sys

# --------------------------------------------------------------------------
# 确定"程序所在目录"（存档、地图都放这里），并优先使用项目自带的 pygame
# --------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    # 打包成 exe 之后：__file__ 指向解包出来的临时目录，
    # 存档和 maps/ 要放在 exe 自己旁边，否则玩家关掉就找不到了
    _HERE = os.path.dirname(os.path.abspath(sys.executable))
else:
    _HERE = os.path.dirname(os.path.abspath(__file__))

_VENDOR = os.path.join(_HERE, "vendor")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

import pygame  # noqa: E402


# ==========================================================================
# 一、全局常量
# ==========================================================================
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 600
WINDOW_SIZE = (WINDOW_WIDTH, WINDOW_HEIGHT)
WINDOW_TITLE = "一箭又一箭"
FPS = 60

# ---- 状态常量（状态机用） ----
STATE_START = "state_start"
STATE_PLAYING = "state_playing"
STATE_WIN = "state_win"
STATE_FAIL = "state_fail"
STATE_TIMEUP = "state_timeup"       # 速度模式时间到
STATE_WORKSHOP = "state_workshop"   # 拓展 / 创意工坊
STATE_VERIFY = "state_verify"       # 文件完整性校验

# ---- 玩法模式 ----
MODE_LEVEL = "level"        # 关卡模式
MODE_ENDLESS = "endless"    # 无尽模式
MODE_SPEED = "speed"        # 速度模式
MODE_CUSTOM = "custom"      # 玩创意工坊里的自定义地图

# ---- 方向常量 ----
DIR_UP = "up"
DIR_RIGHT = "right"
DIR_DOWN = "down"
DIR_LEFT = "left"
DIRECTIONS = (DIR_UP, DIR_RIGHT, DIR_DOWN, DIR_LEFT)

# 【唯一的方向映射】(行增量, 列增量) —— 逻辑判定与图形绘制共用这一份
DIR_STEPS = {
    DIR_UP: (-1, 0),
    DIR_RIGHT: (0, 1),
    DIR_DOWN: (1, 0),
    DIR_LEFT: (0, -1),
}
OPPOSITE = {
    DIR_UP: DIR_DOWN,
    DIR_DOWN: DIR_UP,
    DIR_LEFT: DIR_RIGHT,
    DIR_RIGHT: DIR_LEFT,
}
DIR_LABELS = {DIR_UP: "上", DIR_RIGHT: "右", DIR_DOWN: "下", DIR_LEFT: "左"}

# ---- 配色（深色主题，背景 #1E1E2E） ----
BG_COLOR = (30, 30, 46)
COLOR_TITLE = (255, 255, 255)
COLOR_SUBTITLE = (198, 200, 214)
COLOR_HINT = (150, 152, 168)
COLOR_FOOTNOTE = (120, 122, 138)

COLOR_BUTTON = (62, 122, 226)
COLOR_BUTTON_HOVER = (96, 156, 255)
COLOR_BUTTON_TEXT = (255, 255, 255)
COLOR_BUTTON_ALT = (60, 62, 84)
COLOR_BUTTON_ALT_HOVER = (84, 88, 116)
COLOR_BUTTON_GOLD = (198, 146, 40)
COLOR_BUTTON_GOLD_HOVER = (236, 182, 62)

COLOR_BOARD_BG = (24, 24, 38)
COLOR_CELL_BORDER = (52, 52, 72)
COLOR_BLOCKED = (240, 86, 96)          # 撞击时用（不是预览）
COLOR_HOVER_OUTLINE = (196, 204, 226)  # 悬停只有这一种中性色，不泄漏能不能飞
COLOR_DEBUG_LINK = (110, 114, 146)
COLOR_DEBUG_FREE = (108, 226, 148)
COLOR_SUCCESS = (108, 214, 140)
COLOR_WARN = (255, 200, 96)
COLOR_HEART = (240, 86, 110)
COLOR_HEART_EMPTY = (72, 74, 96)
COLOR_HINT_MARK = (255, 214, 102)      # 提示高亮（注意别和上面的提示文字色重名）

# 箭头调色板：相邻的箭头会被自动分配不同颜色，方便一眼分清"哪些格子属于同一支箭"
ARROW_COLORS = (
    (108, 214, 140),    # 绿
    (98, 168, 255),     # 蓝
    (255, 200, 96),     # 黄
    (255, 138, 96),     # 橙
    (206, 130, 255),    # 紫
    (98, 226, 226),     # 青
    (255, 130, 180),    # 粉
    (170, 196, 224),    # 灰蓝
)

FONT_TITLE = 66
FONT_SUBTITLE = 22
FONT_HINT = 18
FONT_FOOTNOTE = 16
FONT_BODY = 20
FONT_BUTTON = 24
FONT_TINY = 13
FONT_TIMER = 30

# ---- 棋盘参数 ----
BOARD_ROWS = 6
BOARD_COLS = 6
CELL_SIZE = 62          # 上限；格子实际大小会按行列数自动缩放
CELL_GAP = 6
BOARD_AREA = pygame.Rect(0, 86, WINDOW_WIDTH, 448)
MAX_MISTAKES = 3

# ---- 动画 / 玩法参数 ----
FLY_DURATION = 0.42         # 飞出棋盘用多久
WIN_DELAY = 0.55            # 最后一支箭飞出去之后，等这么久再切通关界面
SPEED_WIN_DELAY = 0.20      # 速度模式要快节奏，缓冲短一点
BOUNCE_MIN_TRAVEL = 0.22    # 紧贴着阻挡者时也要"顶一下"的最小行程（单位：格）

SPEED_SECONDS = 60.0        # 速度模式总时长
SPEED_MISTAKE_PENALTY = 3.0  # 速度模式每失误一次扣几秒
SPEED_STAGE = 1             # 速度模式固定用 6x6 的棋盘，保证节奏一致

HINT_DURATION = 2.6         # 提示高亮持续几秒

# ---- 音效 ----
SOUND_RATE = 44100          # 合成与 mixer 都用这个采样率
SOUND_KINDS = ("fly", "hit")
SOUND_STYLES = ("electronic", "wood")
SOUND_STYLE_LABELS = {"electronic": "电子", "wood": "木质"}
SOUND_STYLE_DEFAULT = "electronic"
# 每种音色的合成参数：起始频率、结束频率、时长、音量、波形、衰减指数
# 音量刻意拉开：撞击（hit）明显比飞出（fly）响，玩家一听就知道"撞了"。
SOUND_SPECS = {
    ("electronic", "fly"): dict(f0=420, f1=1180, dur=0.13, vol=0.30,
                                shape="square", decay=2.0),
    ("electronic", "hit"): dict(f0=280, f1=80, dur=0.28, vol=0.92,
                                shape="saw", decay=1.1),
    ("wood", "fly"): dict(f0=880, f1=1320, dur=0.16, vol=0.26,
                          shape="sine", decay=3.2),
    ("wood", "hit"): dict(f0=200, f1=90, dur=0.32, vol=0.85,
                          shape="sine", decay=1.8),
}
# 撞击音至少要比飞出音大这么多倍（自检会按这个比例卡）
SOUND_HIT_MIN_RATIO = 1.8

# 提示 / 撤销 的次数限制：(提示次数, 撤销次数)，None 表示不限次数。
# 关卡模式和自定义地图随便用；无尽和速度模式要限量，不然它们就没有挑战性了。
FEATURE_LIMITS = {
    MODE_LEVEL: (None, None),
    MODE_ENDLESS: (3, 3),
    MODE_SPEED: (2, 2),
    MODE_CUSTOM: (None, None),
}


def feature_limits(mode):
    """返回某个模式下 (提示次数, 撤销次数)；None 表示不限。"""
    return FEATURE_LIMITS.get(mode, (None, None))


# ---- 创意工坊：拓展功能登记表 ----
# 加一个新功能 = ① 这里加一条 ② 在 PlayingScene 里接上行为 ③ 在 Records 里加个 xxx_on 字段。
# （id 同时也是 Records 里 "xxx_on" 这个开关字段的前缀）
FEATURES = (
    {"id": "hint", "title": "提示", "keys": "H", "color": COLOR_HINT_MARK,
     "usage": "游戏中按 H：高亮一支能飞出去的箭头"},
    {"id": "undo", "title": "撤销", "keys": "U · Z", "color": COLOR_SUCCESS,
     "usage": "游戏中按 U 或 Z：退回上一步"},
    {"id": "sound", "title": "音效", "keys": "", "color": (140, 196, 255),
     "usage": "飞出和撞击各一组音色，听哪个顺耳就选哪个"},
)

# ---- 创意工坊：自定义地图 ----
MAPS_DIR = os.path.join(_HERE, "maps")
MAP_SUFFIX = ".json"
EXAMPLE_MAP_FILE = "示例地图.json"
MAP_MAX_SIDE = 12           # 地图最大 12x12，再大格子就太小了

SAVE_FILE = os.path.join(_HERE, "save.json")


def endless_config(stage):
    """无尽模式的难度曲线：(行, 列, 箭最长几格, 尝试摆放次数)。

    尝试次数越多棋盘越密；棋盘和箭长随关数增长。
    """
    if stage <= 2:
        return 6, 6, 4, 170
    if stage <= 5:
        return 7, 7, 4, 280
    if stage <= 9:
        return 8, 8, 5, 420
    return 8, 8, 6, 520


# ==========================================================================
# 二、存档（最佳记录 + 拓展开关）与音效
# ==========================================================================
class Records:
    """玩家存档：最佳记录 + 拓展功能的开关与选项。

    最佳记录：无尽模式最多通过几关、速度模式最多通过几道机关、关卡模式通关数。
    拓展设置：创意工坊里"提示 / 撤销 / 音效"是否启用，以及音效选了哪套音色。

    存档就是一个 json 文件；读不到 / 读坏了都当作从零开始，不影响游戏。
    """

    def __init__(self, path=SAVE_FILE):
        self.path = path
        self.endless = 0          # 无尽模式最佳：通过关数
        self.speed = 0            # 速度模式最佳：通过机关数
        self.levels_cleared = 0   # 关卡模式已通关数量
        self.hint_on = True       # 拓展：提示
        self.undo_on = True       # 拓展：撤销
        self.sound_on = True      # 拓展：音效
        self.sound_style = SOUND_STYLE_DEFAULT
        self.cleared_maps = []    # 自己试玩通关过的自定义地图（内容指纹）
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            self.endless = max(0, int(data.get("endless", 0)))
            self.speed = max(0, int(data.get("speed", 0)))
            self.levels_cleared = max(0, int(data.get("levels_cleared", 0)))
            self.hint_on = bool(data.get("hint_on", True))
            self.undo_on = bool(data.get("undo_on", True))
            self.sound_on = bool(data.get("sound_on", True))
            style = str(data.get("sound_style", SOUND_STYLE_DEFAULT))
            self.sound_style = (style if style in SOUND_STYLES
                                else SOUND_STYLE_DEFAULT)
            self.cleared_maps = [str(code) for code
                                 in data.get("cleared_maps", [])][-64:]
        except (OSError, ValueError, TypeError):
            pass                    # 没有存档 / 存档坏了，从零开始

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as fp:
                json.dump({"endless": self.endless,
                           "speed": self.speed,
                           "levels_cleared": self.levels_cleared,
                           "hint_on": self.hint_on,
                           "undo_on": self.undo_on,
                           "sound_on": self.sound_on,
                           "sound_style": self.sound_style,
                           "cleared_maps": self.cleared_maps},
                          fp, ensure_ascii=False, indent=2)
        except OSError:
            pass                    # 存不了也不影响这次游戏

    def set_hint_on(self, value):
        self.hint_on = bool(value)
        self.save()

    def set_undo_on(self, value):
        self.undo_on = bool(value)
        self.save()

    def set_sound_on(self, value):
        self.sound_on = bool(value)
        self.save()

    def set_sound_style(self, style):
        if style in SOUND_STYLES:
            self.sound_style = style
            self.save()

    # ---- 拓展功能的通用开关（key 就是 FEATURES 里的 id）----
    def feature_on(self, feature_id):
        return bool(getattr(self, feature_id + "_on", True))

    def set_feature_on(self, feature_id, value):
        field = feature_id + "_on"
        if hasattr(self, field):
            setattr(self, field, bool(value))
            self.save()

    # ---- 自定义地图的"我通关过"标记 ----
    def map_cleared(self, level):
        return map_fingerprint(level) in self.cleared_maps

    def mark_map_cleared(self, level):
        """记下"这张图我自己试玩通关过"；返回是不是第一次。"""
        code = map_fingerprint(level)
        if code in self.cleared_maps:
            return False
        self.cleared_maps.append(code)
        self.cleared_maps = self.cleared_maps[-64:]
        self.save()
        return True

    @property
    def endless_unlocked(self):
        """三关全部通关后才解锁无尽模式。"""
        return self.levels_cleared >= len(LEVELS)

    def bump_endless(self, cleared):
        """记一次无尽模式成绩（通过关数），返回是否破纪录。"""
        if cleared > self.endless:
            self.endless = cleared
            self.save()
            return True
        return False

    def bump_speed(self, cleared):
        """记一次速度模式成绩（通过机关数），返回是否破纪录。"""
        if cleared > self.speed:
            self.speed = cleared
            self.save()
            return True
        return False

    def mark_levels_cleared(self, count):
        if count > self.levels_cleared:
            self.levels_cleared = count
            self.save()


def build_wave(style, kind, rate=SOUND_RATE, channels=1):
    """现场合成一小段 16 位 PCM（不依赖任何素材文件）。

    channels 要和 mixer 的实际声道数一致：多声道就把每个采样点重复几遍。
    """
    spec = SOUND_SPECS[(style, kind)]
    total = int(rate * spec["dur"])
    samples = array.array("h")
    phase = 0.0
    for index in range(total):
        u = index / float(max(1, total - 1))
        freq = spec["f0"] + (spec["f1"] - spec["f0"]) * u
        phase += 2.0 * math.pi * freq / rate
        if spec["shape"] == "square":
            value = 1.0 if math.sin(phase) >= 0.0 else -1.0
        elif spec["shape"] == "saw":
            value = 2.0 * ((phase / (2.0 * math.pi)) % 1.0) - 1.0
        else:
            value = math.sin(phase)
        env = (1.0 - u) ** spec["decay"]
        env *= min(1.0, index / 48.0)                  # 起音淡入，防爆音
        env *= min(1.0, (total - index) / 240.0)       # 收尾淡出
        sample = int(max(-1.0, min(1.0, value * env * spec["vol"])) * 32767)
        for _ in range(max(1, channels)):
            samples.append(sample)
    return samples.tobytes()


class SoundKit:
    """音效包：用 pygame.mixer 播放现场合成的两组音色。

    两套音色方案（玩家在创意工坊里选）：
        electronic「电子」 飞出 = 上滑的方波短音；碰撞 = 下坠的锯齿短音
        wood      「木质」 飞出 = 清脆的正弦"叮"；  碰撞 = 低沉的"咚"

    **注意 mixer 的实际格式**：pygame.init() 在有声卡的机器上会先用默认参数
    （通常是 44100/-16/**2 声道**）把 mixer 开好，而 mixer.init() 对已经初始化过的
    mixer 是空操作 —— 如果我们还按单声道去合成，buffer 长度对不上，Sound() 会直接
    抛错、音效静默失效。所以这里先读回真实格式，再按那个格式合成。
    拿不到音频设备时自动降级成静音，游戏照常玩。
    """

    def __init__(self, enabled=True):
        self.ok = False
        self.sounds = {}          # (style, kind) -> pygame.mixer.Sound
        self.last = None          # 最近播放的 (style, kind)，调试与测试可查
        self.format = None        # mixer 实际格式 (频率, 位深, 声道数)
        if not enabled:
            return
        try:
            info = pygame.mixer.get_init()
            if info is not None and info[1] != -16:
                pygame.mixer.quit()          # 位深不是 16 位，重开一个
                info = None
            if info is None:
                pygame.mixer.init(frequency=SOUND_RATE, size=-16, channels=1,
                                  buffer=512)
            info = pygame.mixer.get_init()
            if info is None or info[1] != -16:
                return                       # 真的没有音频设备，静音运行
            self.format = info
            rate, _size, channels = info
            for style in SOUND_STYLES:
                for kind in SOUND_KINDS:
                    self.sounds[(style, kind)] = pygame.mixer.Sound(
                        buffer=build_wave(style, kind, rate, channels))
        except (pygame.error, ValueError):
            self.sounds = {}
            self.ok = False
            return
        self.ok = True

    def play(self, kind, style):
        """播放某个音色下的某种音效；成功返回 True。"""
        if not self.ok:
            return False
        sound = self.sounds.get((style, kind))
        if sound is None:
            return False
        sound.play()
        self.last = (style, kind)
        return True

    def shutdown(self):
        if self.ok:
            try:
                pygame.mixer.quit()
            except pygame.error:
                pass
            self.ok = False


# ==========================================================================
# 三、关卡数据
# ==========================================================================
def arrow(row, col, length, direction):
    """直线箭头：(row, col) 是**箭尾**格子，沿 direction 伸 length 格。"""
    dr, dc = DIR_STEPS[direction]
    return {"cells": [(row + i * dr, col + i * dc) for i in range(length)],
            "direction": direction}


def poly(cells, direction=None):
    """带拐弯的箭头：按给定的格子路径从箭尾走到箭头。

    方向默认取最后一段的方向，所以正常情况下不用自己写；
    只有"一个格子"的箭头才必须显式给 direction。
    """
    return {"cells": [tuple(cell) for cell in cells], "direction": direction}


# === 后续在此处添加关卡数据与切换逻辑 ===
# 想加新关卡：往 LEVELS 里追加一个字典即可。
#   arrow(行, 列, 长度, 方向)  直线箭头
#   poly([(r,c), (r,c), ...])  折线箭头（内部可以拐弯）
# 每关的可解性会在自检里用 Board.is_solvable() 逐个校验。
LEVELS = [
    {
        # 入门：全是直线箭头，只有一处先后依赖（左上那支被右边那支挡着）
        "name": "第 1 关 · 热身",
        "rows": 6, "cols": 6,
        "max_mistakes": 3,
        "arrows": [
            arrow(0, 0, 3, DIR_RIGHT),
            arrow(0, 4, 2, DIR_RIGHT),
            arrow(2, 0, 2, DIR_DOWN),
            arrow(2, 2, 2, DIR_RIGHT),
            arrow(4, 4, 2, DIR_LEFT),
            arrow(5, 1, 3, DIR_RIGHT),
        ],
    },
    {
        # 进阶：摆成"回"字，先拆外圈才动得了里面；
        # 左下那支是**会拐弯**的箭头（先往下、再往右），用来引入折线箭头。
        "name": "第 2 关 · 环环相扣",
        "rows": 6, "cols": 6,
        "max_mistakes": 3,
        "arrows": [
            arrow(0, 0, 4, DIR_RIGHT),
            arrow(0, 4, 2, DIR_RIGHT),
            arrow(1, 0, 4, DIR_DOWN),
            arrow(1, 5, 4, DIR_DOWN),
            arrow(1, 2, 2, DIR_DOWN),
            arrow(2, 3, 2, DIR_RIGHT),
            arrow(4, 2, 2, DIR_RIGHT),
            poly([(4, 1), (5, 1), (5, 2), (5, 3), (5, 4)]),
        ],
    },
    {
        # 困难：8x8 密集棋盘，13 支箭里有 7 支是带拐弯的折线。
        # 这一份是"倒放清除顺序"的构造式生成器产出一份后冻结成数据的
        # （生成时就保证可解），可以当作手写关卡时密度/长度的参考。
        "name": "第 3 关 · 密林",
        "rows": 8, "cols": 8,
        "max_mistakes": 3,
        "arrows": [
            poly([(3, 6), (2, 6), (1, 6), (1, 5)]),
            poly([(3, 4), (4, 4), (5, 4), (5, 5), (6, 5)]),
            arrow(7, 5, 3, DIR_LEFT),
            poly([(7, 7), (7, 6), (6, 6), (6, 7)]),
            poly([(6, 2), (5, 2), (5, 3), (4, 3)]),
            poly([(1, 2), (1, 1), (0, 1)]),
            poly([(7, 2), (7, 1), (6, 1), (6, 0)]),
            arrow(4, 5, 3, DIR_RIGHT),
            poly([(2, 4), (2, 3), (2, 2), (3, 2), (3, 1)]),
            arrow(0, 3, 4, DIR_RIGHT),
            arrow(3, 7, 4, DIR_UP),
            arrow(2, 0, 3, DIR_UP),
            arrow(4, 2, 3, DIR_LEFT),
        ],
    },
]


# --------------------------------------------------------------------------
# 自定义地图（创意工坊）：玩家把 .json 丢进 maps/ 目录就能玩
# --------------------------------------------------------------------------
# 文件格式（箭头有两种写法，direction 能省就省）：
# {
#   "name": "地图名", "rows": 6, "cols": 6, "max_mistakes": 3, "author": "谁",
#   "arrows": [
#     {"row": 0, "col": 0, "length": 6, "direction": "right"},   # 直线简写
#     {"cells": [[1,1], [1,2], [1,3], [2,3]]}                    # 折线（朝向自动取最后一段）
#   ]
# }
# rows / cols 不写就按箭头占的格子自动推出来；越界、重叠、箭身断开都会在载入时报错，
# 逛工坊时会直接把错误显示在地图条目上，不会崩。
EXAMPLE_MAP_DATA = {
    "name": "示例：回旋",
    "author": "一箭又一箭",
    "rows": 6, "cols": 6,
    "max_mistakes": 3,
    "arrows": [
        {"row": 0, "col": 0, "length": 6, "direction": "right"},
        {"row": 1, "col": 0, "length": 5, "direction": "down"},
        {"row": 5, "col": 5, "length": 5, "direction": "left"},
        {"row": 1, "col": 5, "length": 4, "direction": "down"},
        {"cells": [[1, 1], [1, 2], [1, 3], [2, 3], [3, 3]]},
        {"cells": [[2, 1], [3, 1], [4, 1], [4, 2]]},
        {"cells": [[1, 4], [2, 4], [3, 4]]},
    ],
}


def normalize_level(raw, fallback_name="自定义地图"):
    """把玩家写的关卡数据补齐成 Board.load_level() 能吃的形式。

    校验只做"能不能理解"，几何上的越界 / 重叠 / 箭身断开交给 Board 去报错。
    """
    if not isinstance(raw, dict):
        raise ValueError("地图文件的顶层必须是一个 JSON 对象")
    arrows_raw = raw.get("arrows")
    if not isinstance(arrows_raw, list) or not arrows_raw:
        raise ValueError("地图里一支箭头都没有（arrows 是空的）")

    specs = []
    max_row = max_col = -1
    for index, item in enumerate(arrows_raw):
        if not isinstance(item, dict):
            raise ValueError("第 %d 支箭头不是对象" % (index + 1))
        direction = item.get("direction")
        if direction is not None and direction not in DIR_STEPS:
            raise ValueError("第 %d 支箭头的方向 %r 不认识（只能是 %s）"
                             % (index + 1, direction, "/".join(DIRECTIONS)))
        if "cells" in item:
            try:
                cells = [(int(cell[0]), int(cell[1])) for cell in item["cells"]]
            except (TypeError, IndexError, ValueError):
                raise ValueError("第 %d 支箭头的 cells 写错了，应该是 [[行,列], ...]"
                                 % (index + 1))
            if not cells:
                raise ValueError("第 %d 支箭头没有格子" % (index + 1))
        elif "row" in item and "col" in item and "length" in item:
            if direction is None:
                raise ValueError("第 %d 支箭头用了简写，就必须写 direction"
                                 % (index + 1))
            dr, dc = DIR_STEPS[direction]
            length = int(item["length"])
            if length < 1:
                raise ValueError("第 %d 支箭头的 length 至少是 1" % (index + 1))
            cells = [(int(item["row"]) + i * dr, int(item["col"]) + i * dc)
                     for i in range(length)]
        else:
            raise ValueError("第 %d 支箭头既没有 cells，也没有 row/col/length"
                             % (index + 1))

        for (row, col) in cells:
            if row < 0 or col < 0:
                raise ValueError("第 %d 支箭头的格子跑到负数了：%s"
                                 % (index + 1, (row, col)))
            max_row = max(max_row, row)
            max_col = max(max_col, col)
        specs.append({"cells": cells, "direction": direction})

    rows = int(raw.get("rows", max_row + 1))
    cols = int(raw.get("cols", max_col + 1))
    if rows < 1 or cols < 1:
        raise ValueError("棋盘尺寸不合法：%dx%d" % (rows, cols))
    if rows > MAP_MAX_SIDE or cols > MAP_MAX_SIDE:
        raise ValueError("棋盘最多 %dx%d，这张是 %dx%d，格子会小到看不清"
                         % (MAP_MAX_SIDE, MAP_MAX_SIDE, rows, cols))

    return {"name": str(raw.get("name", fallback_name)),
            "author": str(raw.get("author", "")),
            "rows": rows, "cols": cols,
            "max_mistakes": max(1, int(raw.get("max_mistakes", MAX_MISTAKES))),
            "arrows": specs}


def load_map_file(path):
    """读一个地图文件，返回 (关卡数据, None)；出错返回 (None, 错误说明)。"""
    try:
        with open(path, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
    except (OSError, ValueError) as exc:
        return None, "读取失败：%s" % exc
    try:
        return normalize_level(raw), None
    except (ValueError, TypeError) as exc:
        return None, "格式不对：%s" % exc


def scan_maps(area=None):
    """扫描 maps/ 目录，返回地图清单（含每张能否载入、是否可解）。"""
    items = []
    if not os.path.isdir(MAPS_DIR):
        return items
    for filename in sorted(os.listdir(MAPS_DIR)):
        if not filename.lower().endswith(MAP_SUFFIX):
            continue
        path = os.path.join(MAPS_DIR, filename)
        level, error = load_map_file(path)
        entry = {"file": filename, "path": path, "level": level, "error": error}
        if level is not None:
            board = Board(area if area is not None else BOARD_AREA)
            try:
                board.load_level(level)
                entry["arrows"] = board.remaining
                entry["rows"] = board.rows
                entry["cols"] = board.cols
                entry["solvable"] = board.is_solvable()
            except ValueError as exc:
                entry["level"] = None
                entry["error"] = "摆不下：%s" % exc
        items.append(entry)
    return items


def write_example_map(path=None):
    """把示例地图写到 maps/ 目录（工坊里的「生成示例地图」按钮用它）。"""
    path = path or os.path.join(MAPS_DIR, EXAMPLE_MAP_FILE)
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(EXAMPLE_MAP_DATA, fp, ensure_ascii=False, indent=2)
    return path


def map_fingerprint(level):
    """给一张地图的内容算个短指纹。

    用来记"这张图我自己通关过"。玩家改了文件（尺寸、失误上限、任意一支箭），
    指纹就变了，之前的标记自动失效 —— 不会出现"改完还是已通关"的假象。
    箭头顺序不影响指纹（先做规范化排序）。
    """
    canon = {
        "rows": level["rows"],
        "cols": level["cols"],
        "max_mistakes": level.get("max_mistakes", MAX_MISTAKES),
        "arrows": sorted([[list(cell) for cell in spec["cells"]]
                          for spec in level["arrows"]]),
    }
    payload = json.dumps(canon, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------
# 文件完整性校验（hash）
#
# 玩家拿到游戏之后，可以自己算一遍每个文件的 SHA-256，跟仓库里那份
# CHECKSUMS.txt 对一下，确认文件没有损坏、也没有被人改动过。
#
# 【这个功能能做什么、不能做什么，界面上和文档里都如实写清楚】
#   能：发现文件传输损坏、被随手改过、少传/多传了文件。
#   不能：真正的"防篡改"。因为清单文件和游戏放在一起，能改游戏的人
#         也能顺手把清单改掉（改完之后自己算一遍照样"一致"）。
#         要真正防篡改，得靠数字签名，或者从可信渠道（官方 Release 页）
#         单独取这份清单来比对。
# --------------------------------------------------------------------------
CHECKSUM_FILE = "CHECKSUMS.txt"
HASH_ALGO = "sha256"
# 官方仓库与远程清单地址（玩家可以拿远程清单来比对，这样即使本地清单被改也骗不过）
REPO_URL = "https://github.com/matougui-x/arrow-after-arrow"
REPO_RAW_URL = ("https://raw.githubusercontent.com/matougui-x/arrow-after-arrow"
                "/master/CHECKSUMS.txt")
REMOTE_TIMEOUT = 4.0
# 清单收录范围：自己写的代码 + vendor/ 里的依赖 + 打包好的发行包。
# 玩家自己的存档、maps/ 里自己放的地图都不收录（它们本来就会变）。
HASH_CODE_FILES = ("arrow_puzzle.py", "run_tests.py", "build_exe.py",
                   "requirements.txt")
HASH_EXTRA_FILES = (os.path.join("dist", "ArrowAfterArrow.zip"),)
HASH_EXTRA_DIRS = ("vendor",)
HASH_SKIP_DIRS = ("__pycache__",)
# 这些目录没进仓库（见 .gitignore），所以也不算进清单 ——
# 否则别人克隆下来一校验就会报几百个"文件丢失"。
HASH_SKIP_PATHS = ("vendor/pygame/tests", "vendor/pygame/docs")


def sha256_file(path):
    """算一个文件的 SHA-256（分块读，几十 MB 的依赖也不吃内存）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_targets(root=None):
    """要纳入清单的文件（相对路径）。顺序固定，两边算出来才对得上。"""
    root = root or _HERE
    targets = []
    for rel in HASH_CODE_FILES + HASH_EXTRA_FILES:
        if os.path.isfile(os.path.join(root, rel)):
            targets.append(rel.replace(os.sep, "/"))
    example = os.path.join("maps", EXAMPLE_MAP_FILE)
    if os.path.isfile(os.path.join(root, example)):
        targets.append(example.replace(os.sep, "/"))
    for folder in HASH_EXTRA_DIRS:
        base = os.path.join(root, folder)
        for dirpath, dirnames, filenames in os.walk(base):
            keep = []
            for name in dirnames:
                if name in HASH_SKIP_DIRS:
                    continue
                rel_dir = os.path.relpath(os.path.join(dirpath, name), root)
                if rel_dir.replace(os.sep, "/") in HASH_SKIP_PATHS:
                    continue
                keep.append(name)
            dirnames[:] = keep
            for name in filenames:
                if name.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(dirpath, name)
                targets.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(targets)


def manifest_fingerprint(items):
    """把整份清单再算一个指纹：任何一条内容变了，这个指纹就变。"""
    digest = hashlib.sha256()
    for rel, value in items:
        digest.update(("%s  %s\n" % (value, rel)).encode("utf-8"))
    return digest.hexdigest()


def build_manifest(root=None):
    """返回 ([(相对路径, sha256), ...], 整体指纹)。"""
    root = root or _HERE
    items = [(rel, sha256_file(os.path.join(root, rel)))
             for rel in hash_targets(root)]
    return items, manifest_fingerprint(items)


def write_checksums(path=None, root=None):
    """生成清单文件。改完代码、准备发布时跑一次 `--hash-write`。"""
    root = root or _HERE
    items, fingerprint = build_manifest(root)
    path = path or os.path.join(root, CHECKSUM_FILE)
    lines = [
        "# 《一箭又一箭》文件完整性清单（%s）" % HASH_ALGO.upper(),
        "# 用途：确认下载到的游戏文件有没有损坏、有没有被改动过。",
        "# 校验：python arrow_puzzle.py --verify",
        "# 生成：python arrow_puzzle.py --hash-write",
        "# 收录范围：游戏代码 + vendor/ 依赖（玩家存档、自定义地图、打包产物不在内）。",
        "# 提醒：本清单能发现文件损坏或被随手改动，但它和游戏放在一起 ——",
        "#       能把游戏改掉的人也能顺手把这份清单改掉。真正的防篡改要靠数字签名，",
        "#       或者从可信渠道（官方 Release 页）单独取这份清单来比对。",
        "",
    ]
    for rel, value in items:
        lines.append("%s  %s" % (value, rel))
    lines.append("")
    lines.append("# 指纹（以上清单整体的 %s）：%s" % (HASH_ALGO.upper(), fingerprint))
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write("\n".join(lines) + "\n")
    return {"path": path, "count": len(items), "fingerprint": fingerprint}


def parse_checksums_text(text):
    """把清单文本解析成 ([(相对路径, 哈希)], 指纹)。

    本地文件和从 GitHub 取回来的文本走的是同一套解析，两边不会解析出两种结果。
    """
    items, fingerprint = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if "指纹" in line and "：" in line:
                fingerprint = line.rsplit("：", 1)[1].strip()
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            items.append((parts[1].strip(), parts[0].strip()))
    return items, fingerprint


def read_checksums(path=None):
    """读本地清单，返回 ([(相对路径, 哈希)], 指纹)；没有清单返回 (None, None)。"""
    path = path or os.path.join(_HERE, CHECKSUM_FILE)
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return parse_checksums_text(fp.read())
    except (OSError, UnicodeDecodeError):
        return None, None


def compare_manifest(items, fingerprint=None, root=None):
    """拿一份清单去核对当前文件（本地清单、远程清单都用它）。"""
    root = root or _HERE
    now, now_fingerprint = build_manifest(root)
    current, expected = dict(now), dict(items)
    changed = sorted(r for r in expected
                     if r in current and current[r] != expected[r])
    lost = sorted(r for r in expected if r not in current)
    extra = sorted(r for r in current if r not in expected)
    ok = not (changed or lost or extra)
    return {"state": "ok" if ok else "bad", "fingerprint": now_fingerprint,
            "expected": fingerprint, "changed": changed, "lost": lost,
            "extra": extra, "checked": len(expected), "error": None,
            "source": "local"}


def verify_checksums(path=None, root=None):
    """按本地清单核对当前文件，返回结果字典。"""
    items, fingerprint = read_checksums(path)
    if not items:
        result = compare_manifest([], None, root)
        result.update({"state": "missing", "expected": fingerprint})
        return result
    return compare_manifest(items, fingerprint, root)


def fetch_text(url, timeout=REMOTE_TIMEOUT):
    """取一个网址的文本。返回 (文本, 错误说明)，成功时错误为 None。

    故意只用标准库 urllib，不引第三方依赖；没有网络也不抛异常，
    而是把原因交给调用方，界面照常显示。
    """
    try:
        import urllib.request
    except ImportError as exc:                      # 极端精简的环境
        return None, "当前环境没有 urllib（%s）" % exc
    request = urllib.request.Request(
        url, headers={"User-Agent": "ArrowAfterArrow-integrity-check"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(4 * 1024 * 1024)   # 清单只有几十 KB，留个上限
        return data.decode("utf-8", "replace"), None
    except (OSError, ValueError) as exc:            # 断网/超时/域名解析失败都在这
        return None, "%s：%s" % (type(exc).__name__, exc)


def verify_against_remote(url=REPO_RAW_URL, root=None, timeout=REMOTE_TIMEOUT):
    """从 GitHub 取官方清单，跟本地文件比对。

    这样即使本地的 CHECKSUMS.txt 被一起改掉，也骗不过校验。
    但前提是 HTTPS 和仓库本身可信 —— 真正的防篡改要靠签名，这里没做。
    """
    text, error = fetch_text(url, timeout)
    if error:
        result = compare_manifest([], None, root)
        if "404" in error:
            result.update({"state": "badremote", "source": "remote",
                           "error": "远程没有这份清单（404）：可能还没推到仓库，"
                                    "或分支名不对"})
        else:
            result.update({"state": "offline", "error": error,
                           "source": "remote"})
        return result
    items, fingerprint = parse_checksums_text(text or "")
    if not items:
        result = compare_manifest([], None, root)
        result.update({"state": "badremote", "source": "remote",
                       "error": "取回来的内容里没有可用的清单（网址或分支可能不对）"})
        return result
    result = compare_manifest(items, fingerprint, root)
    result["source"] = "remote"
    return result


def describe_verify(result):
    """把校验结果变成一句人话（界面和命令行都用它）。"""
    state = result["state"]
    if state == "missing":
        return "没有找到 %s，无法比对" % CHECKSUM_FILE
    if state == "offline":
        return "联网校验失败（%s）" % (result.get("error") or "取不到清单")
    if state == "badremote":
        return result.get("error") or "远程清单不可用"
    if state == "ok":
        return "%d 个文件全部一致" % result["checked"]
    parts = []
    if result["changed"]:
        parts.append("%d 个文件被改动" % len(result["changed"]))
    if result["lost"]:
        parts.append("%d 个文件丢失" % len(result["lost"]))
    if result["extra"]:
        parts.append("%d 个文件不在清单里" % len(result["extra"]))
    return "、".join(parts)


# ==========================================================================
# 四、字体（彻底解决中文方块乱码）
# ==========================================================================
FONT_FILE_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)

_FONT_CACHE = {}


def clear_font_cache():
    """丢掉缓存的字体对象。

    pygame.quit() 之后旧的 Font 对象就不能再用了 —— 再用会直接段错误崩掉。
    所以 Game 初始化时清一次、退出时也清一次，
    这样同一个进程里连续开关多局游戏（自动化测试就是这么干的）才不会炸。
    """
    _FONT_CACHE.clear()


def get_font(size, bold=False):
    """加载一个能正常显示中文的字体（带缓存）。"""
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    font = None
    for path in FONT_FILE_CANDIDATES:
        if os.path.isfile(path):
            try:
                font = pygame.font.Font(path, size)
                break
            except (OSError, pygame.error):
                font = None
    if font is None:
        matched = pygame.font.match_font(
            "simhei,microsoftyahei,msyh,simsun,notosanscjksc,arialunicodems"
        )
        if matched:
            font = pygame.font.Font(matched, size)
    if font is None:
        font = pygame.font.Font(None, size)
    if bold:
        font.set_bold(True)

    _FONT_CACHE[key] = font
    return font


# ==========================================================================
# 五、绘制工具
# ==========================================================================
def draw_text(surface, text, size, color, center=None, topleft=None,
              midleft=None, midright=None, bold=False):
    """画一段文字，返回它的 Rect。"""
    image = get_font(size, bold).render(text, True, color)
    rect = image.get_rect()
    if center is not None:
        rect.center = center
    elif topleft is not None:
        rect.topleft = topleft
    elif midleft is not None:
        rect.midleft = midleft
    elif midright is not None:
        rect.midright = midright
    surface.blit(image, rect)
    return rect


def draw_arrow_shape(surface, points, direction, color, size, alpha=255):
    """画一支箭头：**穿过各格中心的折线**当箭杆（自然支持拐弯）+ 三角箭头。

    points 是这条折线的顶点（从箭尾到箭头），方向严格来自 DIR_STEPS，
    和规则判定共用同一份映射。size 是格子边长，用来定粗细和箭头大小。
    """
    if not points:
        return
    dr, dc = DIR_STEPS[direction]
    ux, uy = dc, dr                 # 屏幕上的前进方向
    vx, vy = -dr, dc                # 垂直方向
    size = float(size)

    thickness = max(4, int(size * 0.40))
    half_head = size * 0.36
    head = points[-1]
    tip = (head[0] + ux * size * 0.46, head[1] + uy * size * 0.46)
    base = (head[0] - ux * size * 0.12, head[1] - uy * size * 0.12)

    ox = oy = 0
    blit_at = (0, 0)
    if alpha < 255:
        xs = [p[0] for p in points] + [tip[0]]
        ys = [p[1] for p in points] + [tip[1]]
        margin = size
        box = pygame.Rect(int(min(xs) - margin), int(min(ys) - margin),
                          int(max(xs) - min(xs) + margin * 2),
                          int(max(ys) - min(ys) + margin * 2))
        target = pygame.Surface(box.size, pygame.SRCALPHA)
        ox, oy = box.x, box.y
        blit_at = box.topleft
    else:
        target = surface

    rgba = (color[0], color[1], color[2], max(0, min(255, alpha)))
    local = [(p[0] - ox, p[1] - oy) for p in points]

    if len(local) >= 2:
        pygame.draw.lines(target, rgba, False, local, thickness)
    radius = thickness // 2
    for point in local:                     # 拐点画圆，接缝才圆润
        pygame.draw.circle(target, rgba, (int(point[0]), int(point[1])),
                           radius)
    pygame.draw.polygon(target, rgba, [
        (tip[0] - ox, tip[1] - oy),
        (base[0] - ox + vx * half_head, base[1] - oy + vy * half_head),
        (base[0] - ox - vx * half_head, base[1] - oy - vy * half_head),
    ])

    if target is not surface:
        surface.blit(target, blit_at)


def draw_heart(surface, center, size, color):
    """用几何图形画一颗心（不依赖字体里的 ❤ 字形，任何环境都不会变方块）。"""
    x, y = center
    radius = size / 4.0
    pygame.draw.circle(surface, color,
                       (int(x - radius), int(y - radius * 0.5)), int(radius))
    pygame.draw.circle(surface, color,
                       (int(x + radius), int(y - radius * 0.5)), int(radius))
    pygame.draw.polygon(surface, color, [
        (x - radius * 2, y - radius * 0.3),
        (x + radius * 2, y - radius * 0.3),
        (x, y + radius * 1.7),
    ])


class Button:
    """圆角按钮，带鼠标悬停变色效果。"""

    def __init__(self, rect, text, on_click=None, font_size=FONT_BUTTON,
                 base_color=COLOR_BUTTON, hover_color=COLOR_BUTTON_HOVER,
                 text_color=COLOR_BUTTON_TEXT, radius=12):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.on_click = on_click
        self.font_size = font_size
        self.base_color = base_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.radius = radius
        self.hovered = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.on_click is not None:
                    self.on_click()
                return True
        return False

    def draw(self, surface):
        self.hovered = self.rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface,
                         self.hover_color if self.hovered else self.base_color,
                         self.rect, border_radius=self.radius)
        if self.hovered:
            pygame.draw.rect(surface, (255, 255, 255), self.rect, width=2,
                             border_radius=self.radius)
        draw_text(surface, self.text, self.font_size, self.text_color,
                  center=self.rect.center)


def centered_rect(center_x, center_y, width, height):
    return pygame.Rect(center_x - width // 2, center_y - height // 2,
                       width, height)


class Toggle:
    """一个开关（胶囊轨道 + 圆形滑块），创意工坊里用它启用/停用拓展功能。"""

    def __init__(self, rect, value=False, on_change=None):
        self.rect = pygame.Rect(rect)
        self.value = bool(value)
        self.on_change = on_change

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.set(not self.value)
                return True
        return False

    def set(self, value):
        self.value = bool(value)
        if self.on_change is not None:
            self.on_change(self.value)

    def draw(self, surface):
        radius = self.rect.height // 2
        pygame.draw.rect(surface,
                         COLOR_SUCCESS if self.value else COLOR_BUTTON_ALT,
                         self.rect, border_radius=radius)
        pygame.draw.rect(surface, COLOR_CELL_BORDER, self.rect, width=2,
                         border_radius=radius)
        knob = radius - 4
        cx = (self.rect.right - radius) if self.value else (self.rect.left + radius)
        pygame.draw.circle(surface, (255, 255, 255),
                           (int(cx), self.rect.centery), knob)
        draw_text(surface, "已开启" if self.value else "已关闭", FONT_HINT,
                  COLOR_SUBTITLE if self.value else COLOR_HINT,
                  midleft=(self.rect.right + 12, self.rect.centery))


# ==========================================================================
# 六、几何参考实现（慢但绝对正确，用于自检交叉验证）
# ==========================================================================
def scan_occupied(occupied, row, col, direction, rows, cols):
    """沿 direction 逐格前进，返回第一个被占用的格子；畅通返回 None。"""
    dr, dc = DIR_STEPS[direction]
    r, c = row + dr, col + dc
    while 0 <= r < rows and 0 <= c < cols:
        if (r, c) in occupied:
            return (r, c)
        r += dr
        c += dc
    return None


def head_ray_can_fly(cells, direction, blockers, rows, cols):
    """几何参考实现（"沿轨道走"模型）：只有**箭头**会进入新格子。

    所以能不能飞，只看箭头前方那条射线上有没有"别人家的"格子。
    blockers 应该只包含**别的箭**占用的格子。
    """
    row, col = cells[-1]
    dr, dc = DIR_STEPS[direction]
    r, c = row + dr, col + dc
    while 0 <= r < rows and 0 <= c < cols:
        if (r, c) in blockers:
            return False
        r += dr
        c += dc
    return True


# ==========================================================================
# 七、动画与特效
#     箭的运动由 Arrow.offset 驱动（本体真的在动），
#     特效只负责"撞击闪光"这类不改变棋盘状态的装饰。
# ==========================================================================
class FlyOutAnim:
    """飞出棋盘：让 offset 从 0 一路加速涨到 total 格。"""

    def __init__(self, total, duration=FLY_DURATION):
        self.total = float(total)
        self.duration = float(duration)
        self.time = 0.0

    def step(self, dt):
        self.time += dt

    @property
    def offset(self):
        p = min(1.0, self.time / self.duration)
        return self.total * (p ** 1.25)

    @property
    def done(self):
        return self.time >= self.duration


class BounceAnim:
    """撞上去再弹回：offset 走 0 -> travel -> 0（阻尼振荡）。"""

    def __init__(self, travel, travel_cells):
        self.travel = float(travel)
        self.forward_time = min(0.30, 0.15 + 0.035 * max(1.0, travel_cells))
        self.duration = self.forward_time + 0.44
        self.time = 0.0

    def step(self, dt):
        self.time += dt

    @property
    def offset(self):
        if self.time <= self.forward_time:
            u = self.time / self.forward_time
            return self.travel * (u ** 1.7)                    # 加速撞上去
        u = (self.time - self.forward_time) / (self.duration - self.forward_time)
        return self.travel * (1.0 - u) * math.cos(u * math.pi * 2.6)   # 阻尼弹回

    @property
    def done(self):
        return self.time >= self.duration


class ImpactEffect:
    """撞击闪白 + 被撞格子描红（纯装饰，不画箭头本体）。"""

    def __init__(self, contact_point, blocker_rect, duration=0.42):
        self.contact_point = contact_point
        self.blocker_rect = pygame.Rect(blocker_rect)
        self.duration = float(duration)
        self.time = 0.0

    def update(self, dt):
        self.time += dt

    @property
    def finished(self):
        return self.time >= self.duration

    def draw(self, surface):
        pygame.draw.rect(surface, COLOR_BLOCKED, self.blocker_rect.inflate(2, 2),
                         width=3, border_radius=8)
        k = max(0.0, 1.0 - self.time / (self.duration * 0.55))
        if k > 0.0 and self.contact_point is not None:
            radius = int(5 + 12 * k)
            flash = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(flash, (255, 255, 255, int(210 * k)),
                               (radius, radius), radius)
            surface.blit(flash, (self.contact_point[0] - radius,
                                 self.contact_point[1] - radius))


# ==========================================================================
# 八、CellNode / Arrow / Board
# ==========================================================================
class CellNode:
    """一个被占用的格子（邻居图的节点）。

    neighbors[方向] = 该方向上最近的另一个被占用格子（CellNode 或 None）。
    owner 指向它所属的 Arrow —— 有了它就不需要靠坐标反查归属。
    """

    __slots__ = ("row", "col", "owner", "neighbors")

    def __init__(self, row, col, owner):
        self.row = row
        self.col = col
        self.owner = owner
        self.neighbors = dict((d, None) for d in DIRECTIONS)


class Arrow:
    """一支箭头：一条占若干格、内部可以拐弯的折线。

        cells / tail / head / direction / length / color
        offset     沿自己的轨道前进了多少格（0 = 停在原地）—— 动画期间它就是"本体"
        flying     是否已经飞出棋盘（脱离占用表/邻居图，但对象还在画）
        anim       当前动画（FlyOutAnim / BounceAnim），None 表示静止
    """

    def __init__(self, cells, direction, color):
        self.cells = list(cells)
        self.tail = self.cells[0]
        self.head = self.cells[-1]
        self.direction = direction
        self.length = len(self.cells)
        self.color = color

        self.offset = 0.0
        self.flying = False
        self.anim = None

    @property
    def bends(self):
        """这支箭拐了几个弯（用于展示）。"""
        count = 0
        for i in range(2, len(self.cells)):
            a = (self.cells[i][0] - self.cells[i - 1][0],
                 self.cells[i][1] - self.cells[i - 1][1])
            b = (self.cells[i - 1][0] - self.cells[i - 2][0],
                 self.cells[i - 1][1] - self.cells[i - 2][1])
            if a != b:
                count += 1
        return count

    def __repr__(self):
        return "Arrow(tail=%s, len=%d, dir=%s)" % (self.tail, self.length,
                                                   self.direction)


class Board:
    """棋盘：管理箭头数据列表 + 单元格邻居图。"""

    def __init__(self, area, rows=BOARD_ROWS, cols=BOARD_COLS,
                 max_mistakes=MAX_MISTAKES):
        self.area = pygame.Rect(area)
        self.rows = rows
        self.cols = cols
        self.gap = CELL_GAP
        self.cell_size = CELL_SIZE
        self.max_mistakes = max_mistakes

        self.arrows = []          # 本关所有箭头（含正在飞出去的）
        self.grid = []            # grid[row][col] = Arrow 或 None（只记还在场上的）
        self.cells = {}           # (row, col) -> CellNode（邻居图）
        self.total_arrows = 0
        self.mistakes = 0
        self.clicks = 0
        self.effects = []
        self.level_name = ""
        self.win_delay = 0.0                # 最后一支箭飞出去之后的缓冲
        self.win_delay_time = WIN_DELAY     # 缓冲时长（速度模式会调短）
        self.source = None                  # 本关最初的数据（撤销靠它重建）
        self.hint_arrow = None              # 提示高亮的那支箭
        self.hint_time = 0.0

        self._origin_x = 0
        self._origin_y = 0

    # ------------------------------------------------------------------
    # 8.1 关卡载入
    # ------------------------------------------------------------------
    def load_level(self, level_data):
        """从关卡数据重建整关。

        重开时**所有 Arrow 都是新建的实例**，旧的箭头对象、格子节点、占用表
        全部丢弃，最后调用 rebuild_neighbors() 重新建图。
        """
        self.rows = level_data["rows"]
        self.cols = level_data["cols"]
        self.max_mistakes = level_data.get("max_mistakes", MAX_MISTAKES)
        self.level_name = level_data.get("name", "")
        # 留一份最初的数据：撤销时用它把整张图重建出来（不能只恢复箭头位置）
        self.source = level_data

        self.arrows = []
        self.cells = {}
        self.grid = [[None] * self.cols for _ in range(self.rows)]
        self.mistakes = 0
        self.clicks = 0
        self.effects = []
        self.win_delay = 0.0
        self.hint_arrow = None
        self.hint_time = 0.0

        raw = []
        for spec in level_data["arrows"]:
            cells = [tuple(cell) for cell in spec["cells"]]
            direction = spec.get("direction")
            if len(cells) >= 2:
                step = (cells[-1][0] - cells[-2][0], cells[-1][1] - cells[-2][1])
                derived = None
                for name, value in DIR_STEPS.items():
                    if value == step:
                        derived = name
                if derived is None:
                    raise ValueError("箭身最后一段不是相邻格：%s" % (cells,))
                if direction is not None and direction != derived:
                    raise ValueError("方向 %s 与箭身最后一段 %s 不一致：%s"
                                     % (direction, derived, cells))
                direction = derived
            elif direction is None:
                raise ValueError("只有一个格子的箭头必须写明方向：%s" % (cells,))
            raw.append((cells, direction))

        self._validate(raw)
        for cells, direction in raw:
            self.arrows.append(Arrow(cells, direction, ARROW_COLORS[0]))

        self.rebuild_neighbors()     # 先建图（顺便填好占用表 grid）
        self._assign_colors()        # 再按"谁挨着谁"分配颜色
        self._update_layout()
        self.total_arrows = len(self.arrows)
        return self

    def _validate(self, raw):
        """校验关卡数据：越界 / 重叠 / 自己重复占格 / 箭身不相邻。"""
        used = {}
        for cells, direction in raw:
            for index, cell in enumerate(cells):
                row, col = cell
                if not (0 <= row < self.rows and 0 <= col < self.cols):
                    raise ValueError("箭头的格子 %s 越界了" % (cell,))
                if cell in used:
                    raise ValueError("格子 %s 被两支箭头同时占用" % (cell,))
                if cell in cells[:index]:
                    raise ValueError("同一支箭重复占用了格子 %s" % (cell,))
                used[cell] = True
                if index:
                    prev = cells[index - 1]
                    if abs(cell[0] - prev[0]) + abs(cell[1] - prev[1]) != 1:
                        raise ValueError("箭身断开了：%s 与 %s 不相邻"
                                         % (prev, cell))

    def reset(self, seed=None, stage=1):
        """随机生成一关（无尽 / 速度模式 / 测试用），可解性由构造保证。

        思路：按"倒放的清除顺序"摆箭 —— 摆一支新箭时，它**箭头前方**的射线上
        不能有已摆好的箭。这样摆放顺序的逆序就是一条合法清除顺序。
        """
        rows, cols, max_len, attempts = endless_config(stage)
        rng = random.Random(seed)
        occupied = set()
        specs = []
        for _ in range(attempts):
            got = self._random_path(rng, rows, cols, occupied, max_len)
            if got is None:
                continue
            cells, direction = got
            if not head_ray_can_fly(cells, direction, occupied, rows, cols):
                continue
            occupied.update(cells)
            specs.append({"cells": cells, "direction": direction})

        self.load_level({"name": "随机关卡", "rows": rows, "cols": cols,
                         "max_mistakes": self.max_mistakes, "arrows": specs})
        return self

    @staticmethod
    def _random_path(rng, rows, cols, occupied, max_len, min_len=2):
        """随机游走出一条箭身路径（有一定概率拐弯），返回 (cells, 朝向)。"""
        empty = [(r, c) for r in range(rows) for c in range(cols)
                 if (r, c) not in occupied]
        if not empty:
            return None
        cells = [rng.choice(empty)]
        direction = rng.choice(DIRECTIONS)
        target = rng.randint(min_len, max_len)
        while len(cells) < target:
            order = [direction]
            if rng.random() < 0.45:                # 拐弯
                turns = [d for d in DIRECTIONS
                         if d not in (direction, OPPOSITE[direction])]
                rng.shuffle(turns)
                order = turns + order
            for candidate in order:
                dr, dc = DIR_STEPS[candidate]
                nxt = (cells[-1][0] + dr, cells[-1][1] + dc)
                if not (0 <= nxt[0] < rows and 0 <= nxt[1] < cols):
                    continue
                if nxt in occupied or nxt in cells:
                    continue
                cells.append(nxt)
                direction = candidate
                break
            else:
                break
        if len(cells) < min_len:
            return None
        return cells, direction

    def _assign_colors(self):
        """给每支箭分配颜色：挨着的箭头尽量用不同颜色，方便区分归属。"""
        for index, one in enumerate(self.arrows):
            one.color = ARROW_COLORS[index % len(ARROW_COLORS)]

        for one in self.arrows:
            for cell in one.cells:
                for direction in DIRECTIONS:
                    dr, dc = DIR_STEPS[direction]
                    row, col = cell[0] + dr, cell[1] + dc
                    if not (0 <= row < self.rows and 0 <= col < self.cols):
                        continue
                    other = self.grid[row][col]
                    if other is None or other is one:
                        continue
                    if other.color == one.color:
                        for candidate in ARROW_COLORS:
                            if candidate != one.color:
                                other.color = candidate
                                break

    # ------------------------------------------------------------------
    # 8.2 邻居图
    # ------------------------------------------------------------------
    def rebuild_neighbors(self):
        """根据当前箭头列表重建整张邻居图（行内左右串联、列内上下串联）。"""
        self.grid = [[None] * self.cols for _ in range(self.rows)]
        self.cells = {}
        for one in self.arrows:
            if one.flying:                     # 正在飞出去的已经不在场上
                continue
            for (row, col) in one.cells:
                self.grid[row][col] = one
                self.cells[(row, col)] = CellNode(row, col, one)

        for row in range(self.rows):
            prev = None
            for col in range(self.cols):
                node = self.cells.get((row, col))
                if node is None:
                    continue
                if prev is not None:
                    prev.neighbors[DIR_RIGHT] = node
                    node.neighbors[DIR_LEFT] = prev
                prev = node
        for col in range(self.cols):
            prev = None
            for row in range(self.rows):
                node = self.cells.get((row, col))
                if node is None:
                    continue
                if prev is not None:
                    prev.neighbors[DIR_DOWN] = node
                    node.neighbors[DIR_UP] = prev
                prev = node

    def _unlink_cell(self, node):
        """把一个格子从邻居图里摘掉：上下对接、左右对接。"""
        for axis in ((DIR_UP, DIR_DOWN), (DIR_LEFT, DIR_RIGHT)):
            near, far = node.neighbors[axis[0]], node.neighbors[axis[1]]
            if near is not None:
                near.neighbors[axis[1]] = far
            if far is not None:
                far.neighbors[axis[0]] = near

    def verify_neighbors(self):
        """交叉验证：邻居图 与 几何扫描是否完全一致。返回 (是否一致, 说明)。"""
        occupied = set(self.cells.keys())
        for (row, col), node in self.cells.items():
            for direction in DIRECTIONS:
                neighbor = node.neighbors[direction]
                fast = None if neighbor is None else (neighbor.row,
                                                      neighbor.col)
                slow = scan_occupied(occupied, row, col, direction,
                                     self.rows, self.cols)
                if fast != slow:
                    return False, ("cell=(%d,%d) dir=%s 邻居图=%s 扫描=%s"
                                   % (row, col, direction, fast, slow))
        return True, None

    def verify_move_rule(self):
        """交叉验证：邻居图版的 can_fly 与几何扫描版的 head_ray_can_fly 是否一致。"""
        occupied = set(self.cells.keys())
        for one in self.arrows:
            if one.flying:
                continue
            others = set(c for c in occupied if c not in set(one.cells))
            slow = head_ray_can_fly(one.cells, one.direction, others,
                                    self.rows, self.cols)
            if self.can_fly(one) != slow:
                return False, ("%s 邻居图判定=%s 几何判定=%s"
                               % (one, self.can_fly(one), slow))
        return True, None

    # ------------------------------------------------------------------
    # 8.3 坐标换算
    # ------------------------------------------------------------------
    def _update_layout(self):
        """按行列数自动缩放格子，保证棋盘始终塞得进 BOARD_AREA。"""
        fit_w = (self.area.width - (self.cols - 1) * self.gap) // self.cols
        fit_h = (self.area.height - (self.rows - 1) * self.gap) // self.rows
        self.cell_size = max(22, min(CELL_SIZE, fit_w, fit_h))

        board_w = self.cols * self.cell_size + (self.cols - 1) * self.gap
        board_h = self.rows * self.cell_size + (self.rows - 1) * self.gap
        self._origin_x = self.area.x + (self.area.width - board_w) // 2
        self._origin_y = self.area.y + (self.area.height - board_h) // 2

    def board_rect(self):
        board_w = self.cols * self.cell_size + (self.cols - 1) * self.gap
        board_h = self.rows * self.cell_size + (self.rows - 1) * self.gap
        return pygame.Rect(self._origin_x, self._origin_y, board_w, board_h)

    def cell_rect(self, row, col):
        return pygame.Rect(
            self._origin_x + col * (self.cell_size + self.gap),
            self._origin_y + row * (self.cell_size + self.gap),
            self.cell_size,
            self.cell_size,
        )

    def cell_at(self, pos):
        """屏幕坐标 -> (row, col)；不在棋盘上返回 None。"""
        if not self.area.collidepoint(pos):
            return None
        col = (pos[0] - self._origin_x) // (self.cell_size + self.gap)
        row = (pos[1] - self._origin_y) // (self.cell_size + self.gap)
        if 0 <= row < self.rows and 0 <= col < self.cols:
            if self.cell_rect(row, col).collidepoint(pos):
                return (row, col)
        return None

    def arrow_at(self, pos):
        """屏幕上这一点落在哪支箭身上（点箭头任意一格都算）。"""
        cell = self.cell_at(pos)
        if cell is None:
            return None
        return self.grid[cell[0]][cell[1]]

    # ------------------------------------------------------------------
    # 8.4 轨道与动画：箭是"沿自己的轨道走"，不是整体刚性平移
    # ------------------------------------------------------------------
    def rail_points(self, one):
        """返回 (轨道点列表, 箭尾在轨道里的下标)。

        轨道 = 箭身自己的格子 + 向后延长一段 + 向前延长一段：
            · 向前沿箭头朝向延长 —— 头部先直行，后面的拐弯一点点被拉直；
            · 向后沿"箭尾指向第 2 格"的反方向延长 —— 弹回的过冲（offset 为负）也画得出来。
        """
        dr, dc = DIR_STEPS[one.direction]
        if one.length >= 2:
            br = one.cells[0][0] - one.cells[1][0]
            bc = one.cells[0][1] - one.cells[1][1]
        else:
            br, bc = -dr, -dc
        span = one.length + max(self.rows, self.cols) + 2

        cells = []
        r, c = one.tail
        for _ in range(span):
            r += br
            c += bc
            cells.append((r, c))
        cells.reverse()
        tail_index = len(cells)
        cells.extend(one.cells)
        r, c = one.head
        for _ in range(span):
            r += dr
            c += dc
            cells.append((r, c))
        return [self.cell_rect(a, b).center for (a, b) in cells], tail_index

    def arrow_points(self, one):
        """这支箭此刻应该画成的那条折线（已经把 offset 算进去了）。"""
        if one.offset == 0.0:
            return [self.cell_rect(a, b).center for (a, b) in one.cells]

        rail, tail_index = self.rail_points(one)
        last = len(rail) - 1
        points = []
        for index in range(one.length):
            t = tail_index + one.offset + index
            if t <= 0.0:
                points.append(rail[0])
                continue
            if t >= last:
                points.append(rail[last])
                continue
            base = int(math.floor(t))
            frac = t - base
            x0, y0 = rail[base]
            x1, y1 = rail[base + 1]
            points.append((x0 + (x1 - x0) * frac, y0 + (y1 - y0) * frac))
        return points

    def fly_total(self, one):
        """整支箭完全飞出棋盘需要前进多少格。"""
        dr, dc = DIR_STEPS[one.direction]
        r, c = one.head
        steps = 0
        while 0 <= r < self.rows and 0 <= c < self.cols:
            r += dr
            c += dc
            steps += 1
        return steps + one.length

    # ------------------------------------------------------------------
    # 8.5 核心规则
    # ------------------------------------------------------------------
    def _nearest_other(self, cell, direction, owner):
        """从 cell 沿 direction 找第一个"不属于 owner"的占用格子（跳过自己的箭身）。"""
        node = self.cells.get(cell)
        if node is None:
            return None
        node = node.neighbors[direction]
        while node is not None and node.owner is owner:
            node = node.neighbors[direction]
        return node

    def can_fly(self, one):
        """这支箭现在能不能飞（只看箭头正前方，理由见文件头部说明）。"""
        if one.flying:
            return False
        return self._nearest_other(one.head, one.direction, one) is None

    def blocker_of(self, one):
        """挡住这支箭的那个格子 (row, col)；畅通则返回 None。"""
        node = self._nearest_other(one.head, one.direction, one)
        return None if node is None else (node.row, node.col)

    def travel_and_contact(self, one):
        """被挡住时返回 (还能前进几格, 撞上的那一格)。"""
        dr, dc = DIR_STEPS[one.direction]
        own = set(one.cells)
        steps = 0
        r, c = one.head
        while True:
            r += dr
            c += dc
            if not (0 <= r < self.rows and 0 <= c < self.cols):
                return steps, None                  # 这条线直接飞出去了
            if (r, c) not in own and self.grid[r][c] is not None:
                return steps, (r, c)               # 撞上别的箭
            steps += 1

    def _launch(self, one, animate=True):
        """把这支箭**本体**发射出去。

        立刻脱离占用表和邻居图（不再阻挡别人），但对象自己留在 self.arrows 里
        沿轨道飞出棋盘，飞完再回收 —— 所以场上永远只有"这一支箭"，没有幻影。
        animate=False 时（撤销回放）直接让它消失，不放动画。
        """
        for cell in one.cells:
            node = self.cells.pop(cell, None)
            if node is not None:
                self._unlink_cell(node)
            self.grid[cell[0]][cell[1]] = None

        if not animate:
            self.arrows.remove(one)
            return

        one.flying = True
        one.anim = FlyOutAnim(self.fly_total(one))
        if self.is_cleared():
            self.win_delay = self.win_delay_time     # 让最后一支箭飞出去再切界面

    def click_cell(self, row, col, animate=True):
        """对某个格子执行一次点击 —— 真实操作和撤销回放都走这里。

        返回： 'cleared' / 'blocked' / 'empty' / 'ignored'
        """
        if animate and (self.is_cleared() or self.is_failed()):
            return "ignored"
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return "ignored"

        one = self.grid[row][col]
        if one is None:
            return "empty"

        self.clicks += 1

        # ==============================================================
        # === 后续在此处添加箭头点击与路径检测逻辑 ===
        # 现在用的是单元格邻居图：沿邻居链跳过自己的箭身，看箭头正前方第一个
        # "别人家的"格子是不是 None（几何扫描版见 head_ray_can_fly，用作自检基准）。
        # 后续可扩展：墙/洞/传送门、连锁提示、更复杂的阻挡规则。
        # ==============================================================
        blocker = self.blocker_of(one)

        if blocker is None:
            # ---------- A：前方无阻挡 -> 本体沿自己的轨道飞出棋盘 ----------
            self._launch(one, animate)
            return "cleared"

        # ---------- B：有阻挡 -> 本体冲过去撞一下，再弹回原位 ----------
        self.mistakes += 1

        if animate:
            # === 后续在此处添加飞出与碰撞动画反馈逻辑 ===
            # 注意：动的是**箭头本体**（Arrow.offset），不是另画一个特效，
            #       所以原地不会留下第二支箭。
            travel, hit_cell = self.travel_and_contact(one)
            if hit_cell is None:
                hit_cell = blocker
            travel = max(float(travel), BOUNCE_MIN_TRAVEL)
            one.anim = BounceAnim(travel, travel)

            dr, dc = DIR_STEPS[one.direction]
            step = self.cell_size + self.gap
            head_x, head_y = self.cell_rect(*one.head).center
            contact = (head_x + dc * (travel + 0.5) * step,
                       head_y + dr * (travel + 0.5) * step)
            self.effects.append(ImpactEffect(contact,
                                             self.cell_rect(*hit_cell)))
        return "blocked"

    def handle_click(self, pos):
        """处理一次鼠标左键点击（屏幕坐标）。"""
        cell = self.cell_at(pos)
        if cell is None:
            return "ignored"
        return self.click_cell(cell[0], cell[1], True)

    # ------------------------------------------------------------------
    # 8.6 提示与撤销
    # ------------------------------------------------------------------
    def pick_flyable(self):
        """随便挑一支"现在就能飞出去"的箭头（提示功能用）。没有则返回 None。"""
        candidates = [one for one in self.arrows
                      if not one.flying and self.can_fly(one)]
        return random.choice(candidates) if candidates else None

    def show_hint(self, one, duration=HINT_DURATION):
        """把某支箭高亮出来。"""
        self.hint_arrow = one
        self.hint_time = duration

    def replay(self, history):
        """按"最初那张图 + 点击顺序"整体重放 —— 撤销功能的核心。

        只把箭头放回原位是不够的：邻居图是由箭头列表建出来的，箭头飞走后
        那些格子已经从链上摘掉了。所以这里直接 load_level(最初数据) 把整张图
        重建一遍，再把剩下的操作安静地重放，得到的就是"当时那个局面"。
        （这也正是"只记最初状态 + 操作顺序"这个做法的好处：
          不用为每一步深拷贝快照，也不用单独维护邻居变更日志。）
        """
        self.load_level(self.source)
        for (row, col, _was_blocked) in history:
            self.click_cell(row, col, animate=False)
        return self

    # ------------------------------------------------------------------
    # 8.6 状态查询
    # ------------------------------------------------------------------
    @property
    def remaining(self):
        """场上还剩几支箭（正在飞出去的不算）。"""
        return sum(1 for one in self.arrows if not one.flying)

    @property
    def mistakes_left(self):
        return max(0, self.max_mistakes - self.mistakes)

    def is_cleared(self):
        return self.remaining == 0

    def is_failed(self):
        return self.mistakes >= self.max_mistakes

    @property
    def win_ready(self):
        """最后一支箭飞出去了、缓冲时间也过了，可以切通关界面了。"""
        return self.is_cleared() and self.win_delay <= 0.0

    def is_solvable(self):
        """这关能不能被清空（用几何参考实现做贪心，不修改棋盘）。"""
        occupied = set(self.cells.keys())
        alive = [one for one in self.arrows if not one.flying]
        while alive:
            for one in list(alive):
                others = set(c for c in occupied if c not in set(one.cells))
                if head_ray_can_fly(one.cells, one.direction, others,
                                    self.rows, self.cols):
                    for cell in one.cells:
                        occupied.discard(cell)
                    alive.remove(one)
                    break
            else:
                return False
        return True

    # ------------------------------------------------------------------
    # 8.7 更新与绘制
    # ------------------------------------------------------------------
    def update(self, dt):
        """推进所有箭头的动画：本体沿轨道走，走完的飞出箭被回收。"""
        for one in list(self.arrows):
            anim = one.anim
            if anim is None:
                continue
            anim.step(dt)
            one.offset = anim.offset
            if anim.done:
                one.anim = None
                if one.flying:
                    self.arrows.remove(one)     # 完全飞出棋盘，回收对象
                else:
                    one.offset = 0.0            # 弹回原位

        if self.is_cleared() and self.win_delay > 0.0:
            self.win_delay = max(0.0, self.win_delay - dt)

        # 提示高亮：数秒后自己消失；被指点的那支箭飞走了也立刻取消
        if self.hint_arrow is not None:
            self.hint_time -= dt
            if (self.hint_time <= 0.0 or self.hint_arrow.flying
                    or self.hint_arrow not in self.arrows):
                self.hint_arrow = None
                self.hint_time = 0.0

        for effect in self.effects:
            effect.update(dt)
        self.effects = [e for e in self.effects if not e.finished]

    def draw(self, surface, mouse_pos=None, debug_neighbors=False):
        """画棋盘：底板 + 暗格 + 箭头（含正在飞的）+ 悬停提示 + 特效。"""
        pygame.draw.rect(surface, COLOR_BOARD_BG,
                         self.board_rect().inflate(self.gap * 2, self.gap * 2),
                         border_radius=12)

        for row in range(self.rows):
            for col in range(self.cols):
                if self.grid[row][col] is None:
                    pygame.draw.rect(surface, COLOR_CELL_BORDER,
                                     self.cell_rect(row, col), width=1,
                                     border_radius=6)

        for one in self.arrows:
            if not one.flying:
                draw_arrow_shape(surface, self.arrow_points(one),
                                 one.direction, one.color, self.cell_size)
        for one in self.arrows:                 # 正在飞出去的画在最上层
            if one.flying:
                draw_arrow_shape(surface, self.arrow_points(one),
                                 one.direction, one.color, self.cell_size)

        hovered = self.arrow_at(mouse_pos) if mouse_pos is not None else None
        if hovered is not None:
            self._draw_hover(surface, hovered)

        if self.hint_arrow is not None:
            self._draw_hint(surface)

        for effect in self.effects:
            effect.draw(surface)

        if debug_neighbors:
            self.draw_debug_neighbors(surface)

    def _draw_hint(self, surface):
        """提示高亮：给被指点的那支箭套一圈会呼吸的金色描边。"""
        pulse = 0.5 + 0.5 * math.sin(self.hint_time * 9.0)
        glow = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        for (row, col) in self.hint_arrow.cells:
            rect = self.cell_rect(row, col)
            pygame.draw.rect(glow, COLOR_HINT_MARK + (int(36 + 40 * pulse),),
                             rect, border_radius=10)
        surface.blit(glow, (0, 0))
        for (row, col) in self.hint_arrow.cells:
            rect = self.cell_rect(row, col)
            pygame.draw.rect(surface, COLOR_HINT_MARK, rect.inflate(4, 4),
                             width=3 + int(2 * pulse), border_radius=10)

    def _draw_hover(self, surface, one):
        """悬停只提示"我指的是哪一支箭"，用中性色描一圈。

        **刻意不显示能不能飞**（早先的红/绿预览框已经去掉）：
        否则玩家只要看颜色就行了，谜题就不成立 —— 该由玩家自己看盘面判断。
        """
        for (row, col) in one.cells:
            pygame.draw.rect(surface, COLOR_HOVER_OUTLINE,
                             self.cell_rect(row, col), width=3,
                             border_radius=8)

    def draw_debug_neighbors(self, surface):
        """调试叠加（按 D 切换）：把每个格子四个方向的邻居画出来。

        绿线 = 该方向没人挡；红线 = 那是某支箭的"正前方"且被挡；
        灰线 = 指向该方向上最近的邻居。**只给开发看，正常玩不要开。**
        """
        blocked_heads = set(one.head for one in self.arrows
                            if not one.flying and not self.can_fly(one))
        for (row, col), node in self.cells.items():
            cx, cy = self.cell_rect(row, col).center
            for direction in DIRECTIONS:
                dr, dc = DIR_STEPS[direction]
                occupied = node.neighbors[direction] is not None
                if occupied:
                    is_blocked_here = ((row, col) in blocked_heads
                                       and direction == node.owner.direction)
                    color = COLOR_BLOCKED if is_blocked_here else COLOR_DEBUG_LINK
                    length = self.cell_size * 0.45
                else:
                    color = COLOR_DEBUG_FREE
                    length = self.cell_size * 0.28
                pygame.draw.line(surface, color, (cx, cy),
                                 (cx + dc * length, cy + dr * length), 2)


# ==========================================================================
# 九、状态界面（Scene）
# ==========================================================================
class Scene:
    """所有界面的基类。状态切换一律走 self.game.change_state(...)。"""

    def __init__(self, game):
        self.game = game

    def on_enter(self, **payload):
        """进入本状态时调用，payload 由 change_state() 带过来。"""

    def handle_event(self, event):
        return False

    def update(self, dt):
        """dt 为距上一帧的秒数。"""

    def draw(self, surface):
        raise NotImplementedError


class StartScene(Scene):
    """开始界面：标题 + 操作提示 + 三个模式按钮 + 最佳记录。

    注意：红/绿"能不能飞"的预览已经在棋盘里去掉了，首页也没提这回事。
    """

    def __init__(self, game):
        Scene.__init__(self, game)
        cx = WINDOW_WIDTH // 2
        self.main_button = Button(centered_rect(cx, 292, 300, 56),
                                  "开始游戏", self.start_level_mode)
        self.speed_button = Button(centered_rect(cx - 132, 360, 252, 50),
                                   "速度模式", self.start_speed)
        self.endless_button = Button(centered_rect(cx + 132, 360, 252, 50),
                                     "无尽模式", self.start_endless,
                                     base_color=COLOR_BUTTON_ALT,
                                     hover_color=COLOR_BUTTON_ALT_HOVER)
        self.workshop_button = Button(centered_rect(cx - 136, 420, 248, 46),
                                      "拓展 · 创意工坊", self.open_workshop,
                                      base_color=COLOR_BUTTON_ALT,
                                      hover_color=COLOR_BUTTON_ALT_HOVER)
        self.verify_button = Button(centered_rect(cx + 136, 420, 248, 46),
                                    "文件校验", self.open_verify,
                                    base_color=COLOR_BUTTON_ALT,
                                    hover_color=COLOR_BUTTON_ALT_HOVER)
        self.buttons = [self.main_button, self.speed_button,
                        self.endless_button, self.workshop_button,
                        self.verify_button]

    # ---- 模式 ----
    def start_level_mode(self):
        scene = self.game.scenes[STATE_PLAYING]
        scene.mode = MODE_LEVEL
        scene.level_index = self.game.start_level
        scene.set_limits(*feature_limits(MODE_LEVEL))    # 关卡模式不限次数
        self.game.change_state(STATE_PLAYING)

    def start_endless(self):
        self.game.start_endless()

    def start_speed(self):
        self.game.start_speed()

    def open_workshop(self):
        self.game.change_state(STATE_WORKSHOP)

    def open_verify(self):
        self.game.change_state(STATE_VERIFY)

    # ---- 事件 ----
    def handle_event(self, event):
        for button in self.buttons:
            if button.handle_event(event):
                return True
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE,
                                                          pygame.K_RETURN):
            self.start_level_mode()
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_v:
            self.check_integrity()
            return True
        return False

    # ---- 文件完整性 ----
    def check_integrity(self):
        """算一遍每个文件的校验码，跟 CHECKSUMS.txt 比，明细打到控制台。"""
        result = self.game.verify_integrity(force=True)
        print("[校验] %s" % describe_verify(result))
        print("        本地指纹 %s" % (result["fingerprint"] or "（算不出来）"))
        print("        清单指纹 %s" % (result["expected"] or "（没有清单）"))
        for label, keys in (("改动", "changed"), ("丢失", "lost"),
                            ("多余", "extra")):
            for rel in result[keys][:5]:
                print("        %s：%s" % (label, rel))
        return result

    # ---- 绘制 ----
    def draw(self, surface):
        surface.fill(BG_COLOR)
        cx = WINDOW_WIDTH // 2
        records = self.game.records

        draw_text(surface, WINDOW_TITLE, FONT_TITLE, COLOR_TITLE,
                  center=(cx, 112), bold=True)
        draw_text(surface, "点击箭头，清除阻挡，让所有箭头飞出棋盘",
                  FONT_SUBTITLE, COLOR_SUBTITLE, center=(cx, 174))
        draw_text(surface, "箭头是一整条折线，点它身上任意一格都可以",
                  FONT_HINT, COLOR_HINT, center=(cx, 208))
        draw_text(surface, "鼠标左键：点击箭头 · H：提示 · U：撤销 · R：重开 · ESC：返回",
                  FONT_HINT, COLOR_HINT, center=(cx, 234))

        # 无尽模式没解锁时按钮变灰、文案说明解锁条件
        if records.endless_unlocked:
            self.endless_button.text = "无尽模式"
            self.endless_button.base_color = COLOR_BUTTON
            self.endless_button.hover_color = COLOR_BUTTON_HOVER
        else:
            self.endless_button.text = "无尽模式（未解锁）"
            self.endless_button.base_color = COLOR_BUTTON_ALT
            self.endless_button.hover_color = COLOR_BUTTON_ALT

        for button in self.buttons:
            button.draw(surface)

        # ---- 最佳记录 ----
        if records.endless or records.speed or records.levels_cleared:
            line = "最佳记录　无尽 %d 关　·　速度 %d 道　·　关卡 %d/%d" % (
                records.endless, records.speed, records.levels_cleared,
                len(LEVELS))
        else:
            line = "最佳记录　暂无，先来一局吧"
        draw_text(surface, line, FONT_BODY, COLOR_WARN, center=(cx, 468))

        if records.endless_unlocked:
            tip = "速度模式：%d 秒内尽可能多通过机关（失误一次 -%d 秒）" % (
                int(SPEED_SECONDS), int(SPEED_MISTAKE_PENALTY))
        else:
            tip = "通关全部 %d 关后解锁无尽模式" % len(LEVELS)
        draw_text(surface, tip, FONT_FOOTNOTE, COLOR_FOOTNOTE,
                  center=(cx, 498))

        draw_text(surface, "空格 / 回车 也可以开始", FONT_FOOTNOTE,
                  COLOR_FOOTNOTE, center=(cx, 532))

        # ---- 文件完整性：校验码 + 跟清单是否一致（按 V 或进「文件校验」页）----
        result = self.game.integrity
        if result is None:
            official = self.game.official_hash()
            if official:
                text = "文件完整性：点「文件校验」或按 V 用校验码核对（清单 %s…）" % official[:8]
                color = COLOR_FOOTNOTE
            else:
                text = "文件完整性：目录里没有 %s" % CHECKSUM_FILE
                color = COLOR_FOOTNOTE
        elif result["state"] == "ok":
            text = "文件完整性：一致　校验码 %s" % result["fingerprint"][:16]
            color = COLOR_SUCCESS
        elif result["state"] == "missing":
            text = "文件完整性：目录里没有 %s" % CHECKSUM_FILE
            color = COLOR_FOOTNOTE
        else:
            text = "文件完整性：%s（按 V 重查）" % describe_verify(result)
            color = COLOR_BLOCKED
        draw_text(surface, text, FONT_FOOTNOTE, color, center=(cx, 566))


class VerifyScene(Scene):
    """文件完整性校验界面。

    两种比法，区别如实写在界面上：
      · 本地清单 CHECKSUMS.txt —— 快，但改了游戏的人也能顺手把这份清单改掉；
      · GitHub 上的官方清单 —— 本地清单被一起改掉也骗不过，
        代价是依赖 HTTPS 和仓库本身可信。
    想彻底闭合（不依赖"从哪拿清单"）要靠数字签名，本项目没做，这一点也写在界面上。
    """

    def __init__(self, game):
        Scene.__init__(self, game)
        cx = WINDOW_WIDTH // 2
        self.left_rect = pygame.Rect(24, 140, 468, 296)
        self.right_rect = pygame.Rect(508, 140, 468, 296)
        self.local_button = Button(centered_rect(cx - 230, 496, 200, 46),
                                   "本地校验", self.check_local,
                                   base_color=COLOR_BUTTON_ALT,
                                   hover_color=COLOR_BUTTON_ALT_HOVER)
        self.remote_button = Button(centered_rect(cx, 496, 200, 46),
                                    "联网校验", self.check_remote)
        self.repo_button = Button(centered_rect(cx + 230, 496, 200, 46),
                                  "打开仓库页", self.open_repo,
                                  base_color=COLOR_BUTTON_ALT,
                                  hover_color=COLOR_BUTTON_ALT_HOVER)
        self.back_button = Button(centered_rect(cx, 552, 240, 42),
                                  "返回主菜单", self.back,
                                  base_color=COLOR_BUTTON_ALT,
                                  hover_color=COLOR_BUTTON_ALT_HOVER)
        self.buttons = [self.local_button, self.remote_button,
                        self.repo_button, self.back_button]
        self.result = None
        self.message = ""

    def on_enter(self, **payload):
        self.message = ""

    # ---- 动作 ----
    def check_local(self):
        """用仓库里那份 CHECKSUMS.txt 比对。"""
        self.result = verify_checksums()
        self.message = "已用本地清单比对（清单本身也可能被改，见右下说明）"
        return self.result

    def check_remote(self):
        """从 GitHub 取官方清单再比对。"""
        self.result = verify_against_remote()
        state = self.result["state"]
        if state == "offline":
            self.message = "连不上 GitHub，点「打开仓库页」可手动下载清单"
        elif state == "badremote":
            self.message = self.result.get("error") or "远程清单不可用"
        else:
            self.message = "已用 GitHub 上的官方清单比对"
        return self.result

    def open_repo(self):
        """用系统默认浏览器打开仓库页（顺手可以点个 Star）。"""
        try:
            import webbrowser
            opened = webbrowser.open(REPO_URL)
        except Exception as exc:                    # 没有浏览器/权限受限
            print("[校验] 打不开浏览器：%s" % exc)
            opened = False
        if opened:
            self.message = "已打开仓库页：那儿有 CHECKSUMS.txt，顺手点个 Star 更好"
        else:
            self.message = "没能自动打开浏览器，手动访问 %s" % REPO_URL
        print("[校验] 仓库地址：%s" % REPO_URL)
        return opened

    def back(self):
        self.game.change_state(STATE_START)

    # ---- 事件 ----
    def handle_event(self, event):
        for button in self.buttons:
            if button.handle_event(event):
                return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_v:
            self.check_local()
            return True
        return False

    # ---- 绘制 ----
    def draw(self, surface):
        surface.fill(BG_COLOR)
        cx = WINDOW_WIDTH // 2
        draw_text(surface, "文件完整性校验", FONT_TITLE, COLOR_TITLE,
                  center=(cx, 58), bold=True)
        draw_text(surface, "算一遍每个文件的 SHA-256，跟官方清单比对，确认文件没被改动过",
                  FONT_HINT, COLOR_SUBTITLE, center=(cx, 102))

        self.draw_local(surface)
        self.draw_help(surface)

        for button in self.buttons:
            button.draw(surface)

    def draw_local(self, surface):
        """左面板：收录了多少文件、官方指纹、算出来的结论。"""
        rect = self.left_rect
        pygame.draw.rect(surface, COLOR_BOARD_BG, rect, border_radius=14)
        pygame.draw.rect(surface, COLOR_CELL_BORDER, rect, width=2,
                         border_radius=14)
        draw_text(surface, "本地情况", FONT_BODY, COLOR_TITLE,
                  midleft=(rect.left + 18, rect.top + 24))

        listed, listed_hash = read_checksums()
        result = self.result
        rows = [("收录文件数", "%d 个" % len(listed) if listed else "没有清单"),
                ("官方指纹", (listed_hash or "无")[:32])]
        if result is not None:
            rows.append(("本地指纹", (result["fingerprint"] or "算不出来")[:32]))
            rows.append(("比对依据",
                         "GitHub 官方清单" if result["source"] == "remote"
                         else "本地 CHECKSUMS.txt"))
        for index, (key, value) in enumerate(rows):
            y = rect.top + 58 + index * 28
            draw_text(surface, key, FONT_HINT, COLOR_SUBTITLE,
                      midleft=(rect.left + 18, y))
            draw_text(surface, value, FONT_HINT, COLOR_TITLE,
                      midleft=(rect.left + 132, y))

        if result is None:
            state_text, state_color = "结论：还没校验，点下面按钮", COLOR_HINT
        elif result["state"] == "ok":
            state_text = "结论：一致，文件没有被改动过"
            state_color = COLOR_SUCCESS
        else:
            # 面板宽度有限，这里只说结论，详细原因放在下面一行
            short = {"missing": "没有找到本地清单",
                     "offline": "联网校验没成功",
                     "badremote": "远程清单不可用"}.get(result["state"])
            state_text = "结论：%s" % (short or describe_verify(result))
            state_color = COLOR_BLOCKED
        draw_text(surface, state_text, FONT_HINT, state_color,
                  midleft=(rect.left + 18, rect.top + 196))

        if self.message:
            draw_text(surface, self.message, FONT_TINY, COLOR_WARN,
                      midleft=(rect.left + 18, rect.top + 226))
        if result is not None and result["state"] == "bad":
            detail = (result["changed"] + result["lost"] + result["extra"])[:2]
            for index, rel in enumerate(detail):
                draw_text(surface, "· %s" % rel, FONT_TINY, COLOR_BLOCKED,
                          midleft=(rect.left + 18, rect.top + 254 + index * 17))

    def draw_help(self, surface):
        """右面板：自己怎么校验 + 这个功能能做什么、不能做什么。"""
        rect = self.right_rect
        pygame.draw.rect(surface, COLOR_BOARD_BG, rect, border_radius=14)
        pygame.draw.rect(surface, COLOR_CELL_BORDER, rect, width=2,
                         border_radius=14)
        draw_text(surface, "怎么自己校验", FONT_BODY, COLOR_TITLE,
                  midleft=(rect.left + 18, rect.top + 24))
        steps = [
            "1. 项目根目录执行：",
            "     python arrow_puzzle.py --verify",
            "   按本地清单逐项核对，打印「一致 / 不一致」",
            "2. 想跟官方清单比（本地清单被改也骗不过）：",
            "   点下方「联网校验」，或手动下载：",
            "     raw.githubusercontent.com/…/CHECKSUMS.txt",
            "3. 只想看每个文件的校验码：",
            "     python arrow_puzzle.py --hash",
        ]
        for index, line in enumerate(steps):
            draw_text(surface, line, FONT_TINY, COLOR_SUBTITLE,
                      midleft=(rect.left + 18, rect.top + 54 + index * 19))

        draw_text(surface, "能做什么 · 不能做什么", FONT_BODY, COLOR_TITLE,
                  midleft=(rect.left + 18, rect.top + 218))
        notes = [
            ("能", "发现文件损坏、被随手改动、少传多传文件"),
            ("远程清单", "连本地清单被一起改掉也能发现"),
            ("但仍然", "依赖 HTTPS 和仓库本身可信"),
            ("没做的", "数字签名（那才是真正的防篡改）"),
        ]
        for index, (key, value) in enumerate(notes):
            y = rect.top + 246 + index * 17
            color = COLOR_SUCCESS if key == "能" else COLOR_HINT
            draw_text(surface, "· %s：%s" % (key, value), FONT_TINY, color,
                      midleft=(rect.left + 18, y))


class WorkshopScene(Scene):
    """拓展 · 创意工坊 —— 分成「功能」和「地图」两个页签。

    · 功能页：可开关的拓展（提示 / 撤销 / 音效），卡片由 FEATURES 登记表生成，
      开关状态存在 save.json；
    · 地图页：玩家把自己写的 .json 地图丢进 maps/ 目录，这里扫描出来就能直接试玩。
      每张图会现场校验格式、数箭头、判可解性，坏了就把错误显示在条目上，不会崩。

    玩家只需要知道"怎么用"和"文件放哪" —— 内部怎么查邻居图、怎么重放历史、
    怎么合成波形，都不是这个界面要讲的事。
    """

    def __init__(self, game):
        Scene.__init__(self, game)
        records = game.records
        cx = WINDOW_WIDTH // 2

        # ---------------- 顶部页签 ----------------
        self.tab = "feature"
        self.tab_buttons = (
            ("feature", Button(centered_rect(cx - 78, 124, 148, 42), "功能",
                               lambda: self.switch_tab("feature"))),
            ("map", Button(centered_rect(cx + 78, 124, 148, 42), "地图",
                           lambda: self.switch_tab("map"))),
        )
        self.back_button = Button(centered_rect(cx, 552, 240, 44), "返回主菜单",
                                  self.back)

        # ---------------- 「功能」页：卡片由 FEATURES 生成 ----------------
        self.cards = []
        simple = [f for f in FEATURES if f["id"] != "sound"]
        card_w, card_h = 400, 176
        for index, feature in enumerate(simple):
            rect = centered_rect(cx + (index * 2 - 1) * (card_w // 2 + 12),
                                 268, card_w, card_h)
            toggle = Toggle(
                pygame.Rect(rect.centerx - 84, rect.top + 76, 84, 34),
                records.feature_on(feature["id"]),
                lambda value, fid=feature["id"]:
                records.set_feature_on(fid, value))
            self.cards.append((rect, feature, toggle))

        # 音效多一个"选哪套音色"的控件，所以单独一张宽卡片
        self.sound_feature = [f for f in FEATURES if f["id"] == "sound"][0]
        self.sound_rect = centered_rect(cx, 438, 824, 132)
        self.sound_toggle = Toggle(
            pygame.Rect(self.sound_rect.left + 28, self.sound_rect.top + 62,
                        84, 34),
            records.feature_on("sound"),
            lambda value: records.set_feature_on("sound", value))
        self.style_buttons = []
        for index, style in enumerate(SOUND_STYLES):
            rect = centered_rect(cx + 118 + index * 126,
                                 self.sound_rect.top + 42, 112, 40)
            self.style_buttons.append((
                style,
                Button(rect, SOUND_STYLE_LABELS[style],
                       lambda s=style: self.choose_style(s), font_size=20)))

        # ---------------- 「地图」页 ----------------
        self.list_rect = pygame.Rect(25, 176, 430, 276)
        self.info_rect = pygame.Rect(510, 176, 470, 276)
        self.maps = []
        self.selected = None
        self.map_message = ""
        self.row_rects = []
        self.play_button = Button(centered_rect(cx + 240, 496, 200, 46),
                                  "开始游戏", self.play_selected)
        self.refresh_button = Button(centered_rect(cx - 240, 496, 200, 46),
                                     "刷新列表", self.reload_maps,
                                     base_color=COLOR_BUTTON_ALT,
                                     hover_color=COLOR_BUTTON_ALT_HOVER)
        self.example_button = Button(centered_rect(cx, 496, 200, 46),
                                     "生成示例地图", self.make_example,
                                     base_color=COLOR_BUTTON_ALT,
                                     hover_color=COLOR_BUTTON_ALT_HOVER)
        self.map_buttons = [self.play_button, self.refresh_button,
                            self.example_button,
                            self.back_button]

    # ---------------- 生命周期 ----------------
    def on_enter(self, **payload):
        """每次进来都对一下存档里的设置，并重新扫一遍地图目录。"""
        records = self.game.records
        for _rect, feature, toggle in self.cards:
            toggle.value = records.feature_on(feature["id"])
        self.sound_toggle.value = records.feature_on("sound")
        self.reload_maps(quiet=True)

    def switch_tab(self, tab):
        self.tab = tab

    # ---------------- 「地图」页的动作 ----------------
    def reload_maps(self, quiet=False):
        """重新扫描 maps/ 目录。"""
        self.maps = scan_maps(BOARD_AREA)
        self.selected = None
        for index, entry in enumerate(self.maps):
            if entry.get("level") is not None:
                self.selected = index
                break
        if not quiet:
            self.map_message = "扫描完成：找到 %d 张地图" % len(self.maps)

    def make_example(self):
        """把示例地图写到 maps/ 目录，方便玩家照格式改。"""
        try:
            path = write_example_map()
        except OSError as exc:
            self.map_message = "写不进去：%s" % exc
            return
        self.reload_maps(quiet=True)
        self.map_message = "已生成 %s，照它的格式改成你自己的就行" % os.path.basename(path)

    def play_selected(self):
        if self.selected is None or self.selected >= len(self.maps):
            self.map_message = "先在上面点一张地图"
            return
        entry = self.maps[self.selected]
        if entry.get("level") is None:
            self.map_message = "这张地图有问题，先修好再玩：%s" % entry.get("error", "")
            return
        self.game.play_custom_map(entry["level"])

    def choose_style(self, style):
        """选音色，顺手试听一下，玩家能立刻听出区别。"""
        self.game.records.set_sound_style(style)
        self.game.play_sound("fly")

    def back(self):
        self.game.change_state(STATE_START)

    def handle_event(self, event):
        for _tab, button in self.tab_buttons:
            if button.handle_event(event):
                return True
        if self.back_button.handle_event(event):
            return True
        if self.tab == "feature":
            return self._handle_feature_event(event)
        return self._handle_map_event(event)

    def _handle_feature_event(self, event):
        for _style, button in self.style_buttons:      # 音色按钮在卡片里，先判
            if button.handle_event(event):
                return True
        if self.sound_toggle.handle_event(event):
            return True
        for rect, _feature, toggle in self.cards:
            if toggle.handle_event(event):
                return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if rect.collidepoint(event.pos):       # 点卡片任意位置也能开关
                    toggle.set(not toggle.value)
                    return True
        return False

    def _handle_map_event(self, event):
        for button in (self.play_button, self.refresh_button,
                       self.example_button):
            if button.handle_event(event):
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, rect in enumerate(self.row_rects):
                if rect.collidepoint(event.pos):
                    self.selected = index
                    self.map_message = ""
                    return True
        return False

    # ---------------- 绘制 ----------------
    def draw(self, surface):
        surface.fill(BG_COLOR)
        cx = WINDOW_WIDTH // 2

        draw_text(surface, "拓展 · 创意工坊", FONT_TITLE, COLOR_TITLE,
                  center=(cx, 62), bold=True)

        # 页签
        for tab, button in self.tab_buttons:
            active = (tab == self.tab)
            button.base_color = COLOR_BUTTON if active else COLOR_BUTTON_ALT
            button.hover_color = (COLOR_BUTTON_HOVER if active
                                  else COLOR_BUTTON_ALT_HOVER)
            button.draw(surface)

        if self.tab == "feature":
            self._draw_features(surface)
        else:
            self._draw_maps(surface)

        self.back_button.draw(surface)

    def _draw_features(self, surface):
        cx = WINDOW_WIDTH // 2
        records = self.game.records

        draw_text(surface, "打开或关闭你想要的功能", FONT_SUBTITLE,
                  COLOR_SUBTITLE, center=(cx, 160))
        draw_text(surface, "点卡片或开关即可切换；设置会自动保存",
                  FONT_HINT, COLOR_HINT, center=(cx, 186))

        for rect, feature, toggle in self.cards:
            color = feature["color"]
            pygame.draw.rect(surface, COLOR_BOARD_BG, rect, border_radius=14)
            pygame.draw.rect(surface,
                             color if toggle.value else COLOR_CELL_BORDER,
                             rect, width=2, border_radius=14)
            title = feature["title"] + ("　" + feature["keys"]
                                        if feature["keys"] else "")
            draw_text(surface, title, FONT_BUTTON, color,
                      center=(rect.centerx, rect.top + 32))
            toggle.draw(surface)
            draw_text(surface, feature["usage"], FONT_HINT, COLOR_SUBTITLE,
                      center=(rect.centerx, rect.top + 138))

        # ---- 音效卡片（多一个选音色的控件） ----
        rect = self.sound_rect
        color = self.sound_feature["color"]
        pygame.draw.rect(surface, COLOR_BOARD_BG, rect, border_radius=14)
        pygame.draw.rect(surface,
                         color if self.sound_toggle.value
                         else COLOR_CELL_BORDER,
                         rect, width=2, border_radius=14)
        draw_text(surface, self.sound_feature["title"], FONT_BUTTON, color,
                  midleft=(rect.left + 28, rect.top + 26))
        self.sound_toggle.draw(surface)
        draw_text(surface, "音色", FONT_HINT, COLOR_SUBTITLE,
                  midleft=(cx + 8, rect.top + 42))
        for style, button in self.style_buttons:
            active = (style == records.sound_style)
            button.base_color = COLOR_BUTTON if active else COLOR_BUTTON_ALT
            button.hover_color = (COLOR_BUTTON_HOVER if active
                                  else COLOR_BUTTON_ALT_HOVER)
            button.draw(surface)
        draw_text(surface, self.sound_feature["usage"],
                  FONT_HINT, COLOR_HINT, midleft=(rect.left + 28, rect.top + 112))

        draw_text(surface, "次数：关卡模式不限 · 无尽模式每局 %s 次 · 速度模式每局 %s 次"
                  % (feature_limits(MODE_ENDLESS)[0],
                     feature_limits(MODE_SPEED)[0]),
                  FONT_HINT, COLOR_FOOTNOTE, center=(cx, 520))

    def _draw_maps(self, surface):
        """地图页：左边是自己放进去的地图清单，右边是格式说明与目录位置。"""
        cx = WINDOW_WIDTH // 2
        list_rect = self.list_rect
        info_rect = self.info_rect

        draw_text(surface, "把自己写的地图丢进 maps/ 目录，这里就会列出来",
                  FONT_SUBTITLE, COLOR_SUBTITLE, center=(cx, 160))

        # ---- 左边：地图清单 ----
        pygame.draw.rect(surface, COLOR_BOARD_BG, list_rect, border_radius=14)
        pygame.draw.rect(surface, COLOR_CELL_BORDER, list_rect, width=2,
                         border_radius=14)
        draw_text(surface, "地图（%d）" % len(self.maps), FONT_BODY,
                  COLOR_TITLE, midleft=(list_rect.left + 16, list_rect.top + 24))

        self.row_rects = []
        if not self.maps:
            draw_text(surface, "还没有地图", FONT_BODY, COLOR_HINT,
                      center=(list_rect.centerx, list_rect.centery - 16))
            draw_text(surface, "点下面的「生成示例地图」就会放一张进去",
                      FONT_HINT, COLOR_FOOTNOTE,
                      center=(list_rect.centerx, list_rect.centery + 14))
        else:
            for index, entry in enumerate(self.maps[:4]):
                rect = pygame.Rect(list_rect.left + 12,
                                   list_rect.top + 44 + index * 56,
                                   list_rect.width - 24, 50)
                self.row_rects.append(rect)
                chosen = (index == self.selected)
                pygame.draw.rect(surface,
                                 (44, 62, 92) if chosen else (32, 36, 52),
                                 rect, border_radius=10)
                pygame.draw.rect(surface,
                                 COLOR_BUTTON if chosen else COLOR_CELL_BORDER,
                                 rect, width=2, border_radius=10)
                level = entry.get("level")
                name = level["name"] if level else entry["file"]
                draw_text(surface, name, FONT_BODY, COLOR_TITLE,
                          midleft=(rect.left + 12, rect.top + 16))
                if level is None:
                    status, color = entry.get("error", "坏掉了"), COLOR_BLOCKED
                else:
                    status = "%dx%d · %d 支 · %s" % (
                        entry["rows"], entry["cols"], entry["arrows"],
                        "可解" if entry["solvable"] else "可能解不开")
                    color = COLOR_SUCCESS if entry["solvable"] else COLOR_WARN
                    if self.game.records.map_cleared(level):
                        draw_text(surface, "已通关", FONT_TINY, COLOR_SUCCESS,
                                  midright=(rect.right - 12, rect.top + 16))
                draw_text(surface, status, FONT_TINY, color,
                          midleft=(rect.left + 12, rect.top + 36))
            if len(self.maps) > 4:
                draw_text(surface, "……还有 %d 张（列表最多显示 4 张）"
                          % (len(self.maps) - 4), FONT_TINY, COLOR_FOOTNOTE,
                          center=(list_rect.centerx, list_rect.bottom - 16))

        # ---- 右边：格式说明 ----
        pygame.draw.rect(surface, COLOR_BOARD_BG, info_rect, border_radius=14)
        pygame.draw.rect(surface, COLOR_CELL_BORDER, info_rect, width=2,
                         border_radius=14)
        lines = [
            "{",
            '  "name": "我的地图", "rows": 6, "cols": 6,',
            '  "arrows": [',
            '    {"row": 0, "col": 0, "length": 6, "direction": "right"},',
            '    {"cells": [[1,1], [1,2], [1,3], [2,3]]}',
            "  ]",
            "}",
        ]
        draw_text(surface, "地图文件长这样（JSON）", FONT_BODY, COLOR_TITLE,
                  midleft=(info_rect.left + 16, info_rect.top + 22))
        for index, line in enumerate(lines):
            draw_text(surface, line, FONT_TINY, COLOR_SUBTITLE,
                      midleft=(info_rect.left + 16, info_rect.top + 48
                               + index * 19))
        draw_text(surface, "· 折线只要写 cells，方向自动取最后一段",
                  FONT_TINY, COLOR_HINT,
                  midleft=(info_rect.left + 16, info_rect.top + 198))
        draw_text(surface, "· rows / cols 可以省，按箭头占的格子推算",
                  FONT_TINY, COLOR_HINT,
                  midleft=(info_rect.left + 16, info_rect.top + 216))
        draw_text(surface, "· 自己试玩通关过的图会标上「已通关」",
                  FONT_TINY, COLOR_HINT,
                  midleft=(info_rect.left + 16, info_rect.top + 234))
        draw_text(surface, "目录：%s" % MAPS_DIR, FONT_TINY, COLOR_FOOTNOTE,
                  midleft=(info_rect.left + 16, info_rect.top + 254))
        if self.map_message:
            draw_text(surface, self.map_message, FONT_TINY, COLOR_WARN,
                      midleft=(info_rect.left + 16, info_rect.top + 272))

        # ---- 选中信息 + 底部按钮 ----
        if self.selected is not None and self.selected < len(self.maps):
            entry = self.maps[self.selected]
            level = entry.get("level")
            picked = ("选中：%s%s" % (level["name"],
                                    "（%s）" % level["author"]
                                    if level.get("author") else "")
                      if level else "选中：%s（有问题）" % entry["file"])
        else:
            picked = "还没选中地图"
        draw_text(surface, picked, FONT_HINT, COLOR_SUBTITLE,
                  center=(cx, 470))

        self.play_button.base_color = (COLOR_BUTTON if self.selected is not None
                                       and self.maps[self.selected].get("level")
                                       else COLOR_BUTTON_ALT)
        self.play_button.hover_color = (
            COLOR_BUTTON_HOVER if self.selected is not None
            and self.maps[self.selected].get("level") else COLOR_BUTTON_ALT_HOVER)
        for button in (self.play_button, self.refresh_button,
                       self.example_button):
            button.draw(surface)


class PlayingScene(Scene):
    """游戏界面：HUD + 棋盘 + 底部按钮。三种模式共用。"""

    def __init__(self, game, mode=MODE_LEVEL, level_index=0):
        Scene.__init__(self, game)
        self.board = Board(BOARD_AREA)
        self.mode = mode
        self.level_index = level_index
        self.stage = 1               # 无尽 / 速度模式：第几关
        self.cleared = 0             # 无尽 / 速度模式：已经通过几关
        self.custom = None           # 自定义地图模式的关卡数据
        self.time_left = SPEED_SECONDS
        self.debug_neighbors = False

        # 操作历史：只记"点了哪个格子、是不是撞了"，配合 board.source（最初那张图）
        # 就能在任何时候把局面精确重放出来，不需要每步深拷贝快照。
        self.history = []
        hints, undos = feature_limits(mode)
        self.hints_left = hints
        self.undos_left = undos

        cx = WINDOW_WIDTH // 2
        bottom = WINDOW_HEIGHT - 36
        width, gap = 190, 16
        total = 4 * width + 3 * gap
        x0 = cx - total // 2
        centers = [x0 + width // 2 + i * (width + gap) for i in range(4)]
        self.hint_button = Button(centered_rect(centers[0], bottom, width, 44),
                                  "提示 (H)", self.do_hint)
        self.undo_button = Button(centered_rect(centers[1], bottom, width, 44),
                                  "撤销 (U)", self.do_undo)
        self.restart_button = Button(centered_rect(centers[2], bottom, width, 44),
                                     "重开 (R)", self.restart)
        self.back_button = Button(centered_rect(centers[3], bottom, width, 44),
                                  "菜单 (ESC)", self.back_to_menu,
                                  base_color=COLOR_BUTTON_ALT,
                                  hover_color=COLOR_BUTTON_ALT_HOVER)
        self.buttons = [self.hint_button, self.undo_button,
                        self.restart_button, self.back_button]

    # ---- 生命周期 ----
    def on_enter(self, **payload):
        self.restart()

    def restart(self):
        """重开当前这一关（关卡模式重载数据，另外两种模式重新随机）。

        load_level() / reset() 都会丢弃旧的 arrows / cells / grid 再调用
        rebuild_neighbors()，所以不会残留上一局的箭头对象。
        历史记录也一起清掉：重开之后没什么可撤销的。
        """
        self.history = []
        if self.mode == MODE_LEVEL:
            self.board.win_delay_time = WIN_DELAY
            self.board.load_level(LEVELS[self.level_index])
        elif self.mode == MODE_CUSTOM:
            self.board.win_delay_time = WIN_DELAY
            self.board.load_level(self.custom)
        else:
            speed = (self.mode == MODE_SPEED)
            self.board.win_delay_time = SPEED_WIN_DELAY if speed else WIN_DELAY
            stage = SPEED_STAGE if speed else self.stage
            self.board.reset(stage=stage)
            if speed:
                self.board.level_name = "第 %d 道机关" % self.stage
            else:
                self.board.level_name = "无尽模式 · 第 %d 关" % self.stage

    def set_limits(self, hints, undos):
        """由 Game 在开新的一局时调用（无尽 / 速度模式的次数限制按局算）。"""
        self.hints_left = hints
        self.undos_left = undos

    def back_to_menu(self):
        self.game.change_state(STATE_START)

    # ---- 提示 / 撤销 ----
    def can_hint(self):
        if not self.game.records.feature_on("hint"):    # 创意工坊里被停用了
            return False
        if self.hints_left is not None and self.hints_left <= 0:
            return False
        return self.board.pick_flyable() is not None

    def can_undo(self):
        if not self.game.records.feature_on("undo"):    # 创意工坊里被停用了
            return False
        if not self.history:
            return False
        return self.undos_left is None or self.undos_left > 0

    def do_hint(self):
        """提示：遍历盘面，高亮一支 neighbor(direction) 为 None、也就是能安全飞出的箭。"""
        if not self.can_hint():
            return False
        self.board.show_hint(self.board.pick_flyable())
        if self.hints_left is not None:
            self.hints_left -= 1
        return True

    def do_undo(self):
        """撤销：退回上一步。

        不能只把箭头放回原位 —— 邻居图是从箭头列表重建的，箭头飞走后那些格子
        已经摘链了。这里用"最初那张图 + 剩下的点击顺序"整体重放（Board.replay），
        箭头位置、邻居关系、失误数、点击数一起回到当时的样子。
        """
        if not self.can_undo():
            return False
        row, col, was_blocked = self.history.pop()
        self.board.replay(self.history)
        if self.mode == MODE_SPEED and was_blocked:
            # 速度模式里那 -3 秒是这一步带来的，撤销就还回来
            self.time_left = min(SPEED_SECONDS,
                                 self.time_left + SPEED_MISTAKE_PENALTY)
        if self.undos_left is not None:
            self.undos_left -= 1
        return True

    # ---- 胜负 ----
    def check_result(self):
        """胜负判定 —— 状态切换集中在这一个地方。

        通关要等最后一支箭飞出去（board.win_ready）再切界面。
        这个函数可能被"点击"和"每帧 update"两条路径各调一次，
        所以开头就挡掉"已经切走"的情况，保证不会被重复结算。
        """
        if self.game.state != STATE_PLAYING:
            return
        if self.board.is_cleared():
            if not self.board.win_ready:
                return
            if self.mode == MODE_ENDLESS:
                self.cleared += 1
                self.game.records.bump_endless(self.cleared)
                self.game.change_state(STATE_WIN, mode=self.mode,
                                       clicks=self.board.clicks,
                                       mistakes=self.board.mistakes,
                                       has_next=True, finished_all=False,
                                       stage=self.stage, cleared=self.cleared)
            elif self.mode == MODE_CUSTOM:
                # 自己试玩通关了才给它盖上「已通关」，工坊列表里能看出来
                first = self.game.records.mark_map_cleared(self.custom)
                self.game.change_state(STATE_WIN, mode=self.mode,
                                       clicks=self.board.clicks,
                                       mistakes=self.board.mistakes,
                                       has_next=False, finished_all=False,
                                       first_clear=first,
                                       stage=1, cleared=0, level_index=0)
            else:
                has_next = self.level_index + 1 < len(LEVELS)
                if not has_next:
                    self.game.records.mark_levels_cleared(len(LEVELS))
                self.game.change_state(STATE_WIN, mode=self.mode,
                                       clicks=self.board.clicks,
                                       mistakes=self.board.mistakes,
                                       has_next=has_next,
                                       finished_all=not has_next,
                                       stage=1, cleared=0,
                                       level_index=self.level_index)
        elif self.board.is_failed():
            if self.mode == MODE_ENDLESS:
                # 无尽模式失败 = 整局结束，成绩记进最佳记录（不能从这关重来）
                self.game.records.bump_endless(self.cleared)
            self.game.change_state(STATE_FAIL, mode=self.mode,
                                   clicks=self.board.clicks,
                                   cleared=self.cleared, stage=self.stage,
                                   level_index=self.level_index)

    # ---- 事件 ----
    def handle_event(self, event):
        for button in self.buttons:
            if button.handle_event(event):
                return True

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                self.restart()
                return True
            if event.key == pygame.K_ESCAPE:
                self.back_to_menu()
                return True
            if event.key == pygame.K_d:
                self.debug_neighbors = not self.debug_neighbors
                return True
            if event.key == pygame.K_h:            # H：提示
                self.do_hint()
                return True
            if event.key in (pygame.K_u, pygame.K_z):   # U / Z：撤销
                self.do_undo()
                return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            cell = self.board.cell_at(event.pos)
            if cell is None:
                return False
            result = self.board.click_cell(cell[0], cell[1], True)
            if result in ("cleared", "blocked"):
                # 记进历史，撤销时按这个顺序重放
                self.history.append((cell[0], cell[1], result == "blocked"))
                # 音效（飞出 / 撞击各一种，受创意工坊开关控制）
                self.game.play_sound("fly" if result == "cleared" else "hit")
            if result == "blocked" and self.mode == MODE_SPEED:
                # 速度模式：失误直接扣时间
                self.time_left = max(0.0, self.time_left - SPEED_MISTAKE_PENALTY)
            if result != "ignored":
                self.check_result()
                return True
        return False

    # ---- 每帧 ----
    def update(self, dt):
        self.board.update(dt)                       # 推进箭头本体动画

        if self.mode == MODE_SPEED:
            self.time_left -= dt
            if self.board.is_cleared() and self.board.win_ready:
                self.advance_speed()                # 立刻换下一道机关，计时不停
                return
            if self.time_left <= 0.0:
                self.time_left = 0.0
                self.finish_speed()
                return
            return

        if self.board.is_cleared() or self.board.is_failed():
            self.check_result()

    def advance_speed(self):
        """速度模式：通过一道机关，马上换下一道。"""
        self.cleared += 1
        self.stage += 1
        self.restart()

    def finish_speed(self):
        """速度模式：时间到，结算并记录成绩。"""
        is_best = self.game.records.bump_speed(self.cleared)
        self.game.change_state(STATE_TIMEUP, cleared=self.cleared,
                               best=self.game.records.speed, is_best=is_best)

    def draw(self, surface):
        surface.fill(BG_COLOR)
        self.draw_hud(surface)

        self.board.draw(surface, pygame.mouse.get_pos(), self.debug_neighbors)

        self._sync_buttons()
        for button in self.buttons:
            button.draw(surface)

        if self.debug_neighbors:
            draw_text(surface, "邻居图可视化：绿=该方向畅通 红=正前方被挡 灰=邻居"
                               "（开发用，正常玩请按 D 关掉）",
                      FONT_TINY, COLOR_FOOTNOTE, topleft=(28, 8))

    def _sync_buttons(self):
        """按钮上带上剩余次数；被工坊停用 / 次数用完 / 无事可做时变灰。"""
        records = self.game.records
        pairs = ((self.hint_button, "提示 (H)", records.hint_on,
                  self.hints_left, self.can_hint()),
                 (self.undo_button, "撤销 (U)", records.undo_on,
                  self.undos_left, self.can_undo()))
        for button, label, enabled, left, usable in pairs:
            if not enabled:
                button.text = label + " 已关"
            elif left is None:
                button.text = label
            else:
                button.text = "%s %d" % (label, left)
            button.base_color = COLOR_BUTTON if usable else COLOR_BUTTON_ALT
            button.hover_color = (COLOR_BUTTON_HOVER if usable
                                  else COLOR_BUTTON_ALT)

    def draw_hud(self, surface):
        """顶部 HUD，三种模式各有各的重点。"""
        if self.mode == MODE_SPEED:
            self._draw_speed_hud(surface)
            return

        if self.mode == MODE_ENDLESS:
            progress = "无尽模式  第 %d 关（已通过 %d 关）" % (self.stage,
                                                              self.cleared)
        elif self.mode == MODE_CUSTOM:
            progress = "自定义地图"
        else:
            progress = "关卡  %d / %d" % (self.level_index + 1, len(LEVELS))
        draw_text(surface, progress, FONT_BODY, COLOR_TITLE, topleft=(28, 22))
        if self.board.level_name:
            draw_text(surface, self.board.level_name, FONT_HINT, COLOR_HINT,
                      topleft=(28, 50))

        draw_text(surface, "剩余箭头  %d / %d" % (self.board.remaining,
                                                 self.board.total_arrows),
                  FONT_BODY, COLOR_TITLE, center=(WINDOW_WIDTH // 2, 32))

        left = self.board.mistakes_left
        total = self.board.max_mistakes
        base_x = WINDOW_WIDTH - 40
        for index in range(total):
            filled = (total - index) <= left
            draw_heart(surface, (base_x - index * 26, 32), 22,
                       COLOR_HEART if filled else COLOR_HEART_EMPTY)
        draw_text(surface, "失误  %d / %d" % (left, total), FONT_BODY,
                  COLOR_BLOCKED if left == 0 else COLOR_WARN,
                  midright=(base_x - total * 26 - 8, 32))

        # 棋盘上方**不再**写"前方有东西挡着就会撞回来"这类提示：
        # 那等于把规则直接说破，规则在首页交代一次就够了。

    def _draw_speed_hud(self, surface):
        """速度模式 HUD：中间大字倒计时，右边已通过数量。"""
        t = self.time_left
        if t <= 5.0:
            color = COLOR_BLOCKED
        elif t <= 15.0:
            color = COLOR_WARN
        else:
            color = COLOR_TITLE

        draw_text(surface, "速度模式", FONT_BODY, COLOR_SUCCESS,
                  topleft=(28, 22))
        draw_text(surface, "失误 %d 次（每次 -%d 秒）"
                  % (self.board.mistakes, int(SPEED_MISTAKE_PENALTY)),
                  FONT_HINT, COLOR_HINT, topleft=(28, 50))

        draw_text(surface, "%.1f" % t, FONT_TIMER, color,
                  center=(WINDOW_WIDTH // 2, 34))
        draw_text(surface, "秒", FONT_HINT, COLOR_HINT,
                  topleft=(WINDOW_WIDTH // 2 + 46, 24))

        draw_text(surface, "已通过  %d 道" % self.cleared, FONT_BODY,
                  COLOR_SUCCESS, midright=(WINDOW_WIDTH - 40, 32))
        if self.board.level_name:
            draw_text(surface, self.board.level_name, FONT_HINT, COLOR_HINT,
                      midright=(WINDOW_WIDTH - 40, 56))


class ResultScene(Scene):
    """结果界面的公共部分：大标题 + 说明行 + 两个按钮。"""

    bg_color = BG_COLOR
    title = ""
    title_color = COLOR_TITLE
    hint = "空格 / 回车：继续 · ESC：返回主菜单"

    def __init__(self, game):
        Scene.__init__(self, game)
        self.lines = []
        self.buttons = []
        self.primary = None

    def make_buttons(self, primary, secondary):
        """primary / secondary 都是 (文字, 回调, 是否金色) 三元组。"""
        cx = WINDOW_WIDTH // 2
        self.primary = primary[1]
        self.buttons = []
        for offset, (text, action, gold) in ((cx - 122, primary),
                                             (cx + 122, secondary)):
            self.buttons.append(Button(
                centered_rect(offset, 414, 220, 56), text, action,
                base_color=COLOR_BUTTON_GOLD if gold else COLOR_BUTTON,
                hover_color=(COLOR_BUTTON_GOLD_HOVER if gold
                             else COLOR_BUTTON_HOVER)))

    def handle_event(self, event):
        for button in self.buttons:
            if button.handle_event(event):
                return True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                if self.primary is not None:
                    self.primary()
                return True
            if event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_START)
                return True
        return False

    def draw(self, surface):
        surface.fill(self.bg_color)
        cx = WINDOW_WIDTH // 2

        draw_text(surface, self.title, FONT_TITLE, self.title_color,
                  center=(cx, 182), bold=True)
        for index, line in enumerate(self.lines):
            draw_text(surface, line, FONT_BODY, COLOR_SUBTITLE,
                      center=(cx, 264 + index * 32))

        for button in self.buttons:
            button.draw(surface)

        draw_text(surface, self.hint, FONT_FOOTNOTE, COLOR_FOOTNOTE,
                  center=(cx, 480))


class WinScene(ResultScene):
    """通关界面：下一关 / 全部通关后进无尽模式 / 无尽模式继续下一关。"""

    bg_color = BG_COLOR
    title = "通关！"
    title_color = COLOR_SUCCESS

    def on_enter(self, **payload):
        clicks = payload.get("clicks", 0)
        mistakes = payload.get("mistakes", 0)
        has_next = payload.get("has_next", False)
        mode = payload.get("mode", MODE_LEVEL)
        stage = payload.get("stage", 1)
        cleared = payload.get("cleared", 0)

        if mode == MODE_ENDLESS:
            self.title = "第 %d 关 通过！" % stage
            self.lines = ["点击 %d 次，失误 %d 次" % (clicks, mistakes),
                          "已通过 %d 关，最佳记录 %d 关"
                          % (cleared, self.game.records.endless),
                          "无尽模式会越来越难，失败即整局结束"]
            self.make_buttons(("进入下一关", self.next_level, False),
                              ("返回主菜单", self.back_to_menu, False))
        elif mode == MODE_CUSTOM:
            self.title = "通关！"
            self.lines = ["自定义地图清空了",
                          "点击 %d 次，失误 %d 次" % (clicks, mistakes)]
            if payload.get("first_clear"):
                self.lines.append("第一次通过这张图，已给它盖上「已通关」")
            else:
                self.lines.append("这张图你之前已经通关过了")
            self.make_buttons(("再玩一次", self.replay_custom, False),
                              ("返回创意工坊", self.back_to_workshop, False))
        elif has_next:
            self.title = "通关！"
            self.lines = ["本关全部箭头都飞出去了",
                          "点击 %d 次，失误 %d 次" % (clicks, mistakes)]
            self.make_buttons(("进入下一关", self.next_level, False),
                              ("返回主菜单", self.back_to_menu, False))
        else:
            self.title = "全部通关！"
            self.lines = ["%d 个关卡都清空了，厉害" % len(LEVELS),
                          "点击 %d 次，失误 %d 次" % (clicks, mistakes),
                          "解锁了无尽模式：棋盘更大、箭头更长"]
            self.make_buttons(("进入无尽模式", self.enter_endless, True),
                              ("返回主菜单", self.back_to_menu, False))

    def next_level(self):
        """进入下一关（关卡模式）或下一关无尽模式。

        # === 后续在此处添加关卡数据与切换逻辑 ===
        更复杂的关卡表（选关、星级、解锁）都在这里扩展。
        """
        scene = self.game.scenes[STATE_PLAYING]
        if scene.mode == MODE_ENDLESS:
            scene.stage += 1
            self.game.change_state(STATE_PLAYING)
            return
        if scene.level_index + 1 >= len(LEVELS):
            return
        scene.level_index += 1
        self.game.change_state(STATE_PLAYING)

    def enter_endless(self):
        self.game.start_endless()

    def replay_custom(self):
        """再玩一次这张自定义地图。"""
        self.game.change_state(STATE_PLAYING)

    def back_to_workshop(self):
        self.game.change_state(STATE_WORKSHOP)

    def back_to_menu(self):
        self.game.change_state(STATE_START)


class FailScene(ResultScene):
    """失败界面。

    · 关卡模式：重新开始本关 / 返回主菜单
    · 无尽模式：**整局结束**，只能开新的一局（不能从失败的那关重来），
      顺便把这次成绩和最佳记录摆出来
    """

    bg_color = BG_COLOR

    def on_enter(self, **payload):
        mode = payload.get("mode", MODE_LEVEL)
        cleared = payload.get("cleared", 0)
        stage = payload.get("stage", 1)
        clicks = payload.get("clicks", 0)

        if mode == MODE_ENDLESS:
            best = self.game.records.endless
            self.title = "本局结束"
            self.title_color = COLOR_BLOCKED
            self.lines = [
                "在第 %d 关用光了失误次数" % stage,
                "本局通过 %d 关　·　最佳记录 %d 关" % (cleared, best),
            ]
            if cleared >= best and cleared > 0:
                self.lines.append("刷新了最佳记录！")
            self.make_buttons(("再开一局（从第 1 关）", self.restart_endless, True),
                              ("返回主菜单", self.back_to_menu, False))
        else:
            self.title = "挑战失败"
            self.title_color = COLOR_BLOCKED
            self.lines = ["失误次数用完了，还有箭头没能飞出去",
                          "本局点击 %d 次" % clicks]
            self.make_buttons(("重新开始", self.restart_level, False),
                              ("返回主菜单", self.back_to_menu, False))

    def restart_level(self):
        self.game.change_state(STATE_PLAYING)

    def restart_endless(self):
        """无尽模式失败后只能**重新开一局**（从第 1 关开始）。"""
        self.game.start_endless()

    def back_to_menu(self):
        self.game.change_state(STATE_START)


class TimeUpScene(ResultScene):
    """速度模式时间到。"""

    bg_color = BG_COLOR
    title = "时间到！"
    title_color = COLOR_WARN

    def on_enter(self, **payload):
        cleared = payload.get("cleared", 0)
        best = payload.get("best", 0)
        is_best = payload.get("is_best", False)

        self.lines = [
            "%d 秒内通过了 %d 道机关" % (int(SPEED_SECONDS), cleared),
            "最佳记录 %d 道" % best,
        ]
        if is_best and cleared > 0:
            self.lines.append("刷新了最佳记录！")
        self.make_buttons(("再来一次", self.restart_speed, True),
                          ("返回主菜单", self.back_to_menu, False))

    def restart_speed(self):
        self.game.start_speed()

    def back_to_menu(self):
        self.game.change_state(STATE_START)


# ==========================================================================
# 十、Game：窗口、状态机、主循环
# ==========================================================================
class Game:
    """游戏主控：窗口、时钟、状态机、最佳记录、主循环。"""

    def __init__(self, level_index=0, mode=MODE_LEVEL, records_path=SAVE_FILE):
        pygame.init()
        clear_font_cache()          # 重新 init 之后要丢弃旧的字体对象
        pygame.display.set_caption(WINDOW_TITLE)
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        self.clock = pygame.time.Clock()

        self.running = True
        self.start_state = STATE_START
        self.state = STATE_START
        self.start_level = level_index
        self.start_mode = mode
        self.records = Records(records_path)
        self.sound = SoundKit()
        self.integrity = None            # 文件校验结果（按需算，算完缓存）
        self._official_hash = None       # CHECKSUMS.txt 里那份官方指纹

        # 第一次运行（尤其是打包成 exe 之后）先把 maps/ 目录和示例地图准备好，
        # 免得工坊地图页空空如也、玩家也不知道该往哪放文件
        if not os.path.isdir(MAPS_DIR):
            try:
                write_example_map()
            except OSError:
                pass

        self.scenes = {
            STATE_START: StartScene(self),
            STATE_PLAYING: PlayingScene(self, mode, level_index),
            STATE_WIN: WinScene(self),
            STATE_FAIL: FailScene(self),
            STATE_TIMEUP: TimeUpScene(self),
            STATE_WORKSHOP: WorkshopScene(self),
            STATE_VERIFY: VerifyScene(self),
        }
        self.scene.on_enter()

    @property
    def scene(self):
        return self.scenes[self.state]

    def change_state(self, new_state, **payload):
        """切换状态；payload 原样交给新界面的 on_enter()。"""
        if new_state != self.state:
            print("[state] %s -> %s" % (self.state, new_state))
        self.state = new_state
        self.scene.on_enter(**payload)

    def play_sound(self, kind):
        """播放音效（受创意工坊的"音效"开关和音色选择控制）。"""
        if not self.records.feature_on("sound"):
            return False
        return self.sound.play(kind, self.records.sound_style)

    def play_custom_map(self, level_data):
        """玩一张创意工坊里的自定义地图。"""
        scene = self.scenes[STATE_PLAYING]
        scene.mode = MODE_CUSTOM
        scene.custom = level_data
        scene.set_limits(*feature_limits(MODE_CUSTOM))
        self.change_state(STATE_PLAYING)

    # ---- 文件完整性校验 ----
    def official_hash(self):
        """CHECKSUMS.txt 里那份"官方指纹"（读一次就缓存）。"""
        if self._official_hash is None:
            _items, fingerprint = read_checksums()
            self._official_hash = fingerprint or ""
        return self._official_hash

    def verify_integrity(self, force=False):
        """算一遍文件校验码并跟清单比对（含 vendor，约 0.2 秒），结果缓存。"""
        if self.integrity is None or force:
            self.integrity = verify_checksums()
        return self.integrity

    # ---- 三种模式的入口 ----
    def start_endless(self):
        """开一局无尽模式（从第 1 关开始；未解锁则忽略）。"""
        if not self.records.endless_unlocked:
            return
        scene = self.scenes[STATE_PLAYING]
        scene.mode = MODE_ENDLESS
        scene.stage = 1
        scene.cleared = 0
        scene.set_limits(*feature_limits(MODE_ENDLESS))   # 提示/撤销按局限量
        self.change_state(STATE_PLAYING)

    def start_speed(self):
        """开一局速度模式（固定 60 秒，从第 1 道机关开始）。"""
        scene = self.scenes[STATE_PLAYING]
        scene.mode = MODE_SPEED
        scene.stage = 1
        scene.cleared = 0
        scene.time_left = SPEED_SECONDS
        scene.set_limits(*feature_limits(MODE_SPEED))
        self.change_state(STATE_PLAYING)

    # ---- 主循环 ----
    def handle_events(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
                continue
            if self.scene.handle_event(event):
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self.state == STATE_START:
                    self.running = False
                else:
                    self.change_state(STATE_START)

    def update(self, dt):
        self.scene.update(dt)

    def draw(self):
        self.scene.draw(self.screen)
        pygame.display.flip()

    def process_frame(self, events, dt):
        self.handle_events(events)
        self.update(dt)
        self.draw()

    def run(self, max_frames=None):
        frame_count = 0
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.process_frame(pygame.event.get(), dt)
            frame_count += 1
            if max_frames is not None and frame_count >= max_frames:
                break
        self.shutdown()

    def shutdown(self):
        self.sound.shutdown()
        clear_font_cache()          # 先丢字体，再 quit，避免下次复用失效对象
        pygame.quit()


# ==========================================================================
# 十一、自检（python arrow_puzzle.py --selftest）
# ==========================================================================
def _click(game, pos):
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1})
    game.process_frame([event], 1.0 / 60.0)


def _find_flyable(board):
    for one in board.arrows:
        if not one.flying and board.can_fly(one):
            return one
    return None


def _find_blocked(board):
    for one in board.arrows:
        if not one.flying and not board.can_fly(one):
            return one
    return None


def _run_frames(game, count):
    for _ in range(count):
        game.process_frame([], 1.0 / 60.0)


def _clear_level(game, scene, limit=3000):
    """一直点能飞的箭，直到本关通关（把飞出动画和缓冲时间都跑完）。"""
    board = scene.board
    guard = 0
    while game.state == STATE_PLAYING and guard < limit:
        guard += 1
        if not board.is_cleared() or not board.win_ready:
            one = _find_flyable(board)
            if one is not None:
                board.handle_click(board.cell_rect(*one.cells[0]).center)
        game.process_frame([], 1.0 / 60.0)
        scene.check_result()
    return game.state


def _bounding_extent(direction):
    """单格箭头：箭尖必须往朝向那一侧凸出去（包围盒该侧更长）。"""
    dr, dc = DIR_STEPS[direction]
    side = 61
    surf = pygame.Surface((side, side), pygame.SRCALPHA)
    draw_arrow_shape(surf, [surf.get_rect().center], direction,
                     (255, 255, 255), side)
    box = surf.get_bounding_rect()
    if box.width == 0:
        return False, "%s 什么都没画出来" % direction
    forward = (box.right - side // 2) * dc + (box.bottom - side // 2) * dr
    backward = (side // 2 - box.left) * dc + (side // 2 - box.top) * dr
    if forward <= backward:
        return False, ("%s 箭尖没有朝向 DIR_STEPS 指示的方向（前伸=%d 后伸=%d）"
                       % (direction, forward, backward))
    return True, None


def _strip_lit(mask, rect, direction, near_front, band=6):
    """统计某个格子里"靠前缘 / 靠后缘"那条带上的着色像素数。"""
    dr, dc = DIR_STEPS[direction]
    half = rect.width / 2.0
    count = 0
    for y in range(rect.top, rect.bottom):
        for x in range(rect.left, rect.right):
            proj = (x - rect.centerx) * dc + (y - rect.centery) * dr
            if near_front and proj < half - band:
                continue
            if (not near_front) and proj > -half + band:
                continue
            if mask.get_at((x, y)):
                count += 1
    return count


def _check_rendered_directions(board):
    """把整关画出来，逐支箭头核对"图上箭尖朝向 == 数据里的方向"。"""
    surf = pygame.Surface(WINDOW_SIZE)
    surf.fill((0, 0, 0))
    board.draw(surf, None, False)
    for one in board.arrows:
        if one.length < 2:
            continue
        mask = pygame.mask.from_threshold(surf, one.color,
                                          threshold=(30, 30, 30, 255))
        head = board.cell_rect(*one.head)
        front = _strip_lit(mask, head, one.direction, True)
        back = _strip_lit(mask, head, one.direction, False)
        if front >= back:
            return False, ("%s 图形朝向不对（前缘宽=%d 后缘宽=%d）"
                           % (one, front, back))
    return True, None


def _cell_lit(surf, color, rect, threshold=(30, 30, 30, 255)):
    """某个格子里有多少像素是这支箭的颜色。"""
    mask = pygame.mask.from_threshold(surf, color, threshold=threshold)
    count = 0
    for y in range(rect.top, rect.bottom):
        for x in range(rect.left, rect.right):
            if mask.get_at((x, y)):
                count += 1
    return count


def _color_count(surf, color):
    """整张图里某个颜色出现了多少像素。"""
    mask = pygame.mask.from_threshold(surf, color, threshold=(6, 6, 6, 255))
    return mask.count()


def run_selftest():
    os.environ["SDL_VIDEODRIVER"] = "dummy"     # 必须在 pygame.init() 之前
    os.environ["SDL_AUDIODRIVER"] = "dummy"

    # 打包成 --windowed 的 exe 没有控制台，print 会被丢掉；
    # 这种情况下把整份自检报告（含报错回溯）写到程序旁边，方便留证据、报问题。
    report_path = None
    if sys.stdout is None:
        report_path = os.path.join(_HERE, "selftest_report.txt")
        try:
            log = open(report_path, "w", encoding="utf-8")
            sys.stdout = log
            sys.stderr = log
        except OSError:
            report_path = None

    save_path = os.path.join(_HERE, "_selftest_save.json")
    if os.path.isfile(save_path):
        os.remove(save_path)

    game = Game(records_path=save_path)
    board = game.scenes[STATE_PLAYING].board

    # ---------- 1. 图形朝向 == 方向映射 ----------
    for direction in DIRECTIONS:
        ok, why = _bounding_extent(direction)
        assert ok, why
    for level in LEVELS:
        board.load_level(level)
        ok, why = _check_rendered_directions(board)
        assert ok, why
    print("[1] 每支箭的图形朝向 都与数据方向一致（含整关渲染逐支核对）  OK")

    # ---------- 2. 关卡数据合法 ----------
    bend_total = 0
    for level in LEVELS:
        board.load_level(level)
        assert board.rows == level["rows"] and board.cols == level["cols"]
        assert board.remaining == len(level["arrows"])
        bend_total += sum(1 for one in board.arrows if one.bends)
    print("[2] %d 个关卡结构合法（%s），其中 %d 支带拐弯  OK"
          % (len(LEVELS),
             "、".join("%dx%d/%d支" % (lv["rows"], lv["cols"],
                                       len(lv["arrows"])) for lv in LEVELS),
             bend_total))

    # ---------- 3. 所有关卡必须可解 ----------
    for index, level in enumerate(LEVELS):
        board.load_level(level)
        assert board.is_solvable(), "LEVELS[%d] 不可解！" % index
    print("[3] %d 个关卡全部可解  OK" % len(LEVELS))

    # ---------- 4. 邻居图 / 移动规则 vs 几何扫描 ----------
    checked = 0
    for index, level in enumerate(LEVELS):
        board.load_level(level)
        ok, why = board.verify_neighbors()
        assert ok, "关卡 %d 建图后邻居图不一致：%s" % (index, why)
        step = 0
        while step < 300:
            ok, why = board.verify_move_rule()
            assert ok, "关卡 %d 第 %d 步移动规则不一致：%s" % (index, step, why)
            checked += 1
            one = _find_flyable(board)
            if one is None:
                break
            board.handle_click(board.cell_rect(*one.cells[0]).center)
            board.update(1.0 / 60.0)
            ok, why = board.verify_neighbors()
            assert ok, "关卡 %d 第 %d 步拆链后不一致：%s" % (index, step, why)
            step += 1
        while board.remaining > 0:
            board.update(1.0 / 60.0)
        assert board.is_cleared(), "关卡 %d 按贪心清不掉" % index
    for seed in range(15):
        for stage in (1, 4, 8):
            board.reset(seed=seed, stage=stage)
            ok, why = board.verify_neighbors()
            assert ok, "随机关 seed=%d stage=%d 邻居图不一致：%s" % (seed, stage, why)
            ok, why = board.verify_move_rule()
            assert ok, "随机关 seed=%d stage=%d 移动规则不一致：%s" % (seed, stage, why)
            checked += 1
    print("[4] 移动规则与邻居图 始终和几何扫描一致（逐关拆到清空 + 45 个随机关，"
          "共 %d 次校验）  OK" % checked)

    # ---------- 5. 重开不会残留旧对象 ----------
    board.load_level(LEVELS[0])
    old_arrows = list(board.arrows)
    old_nodes = dict(board.cells)
    old_ids = set(id(a) for a in board.arrows)
    board.load_level(LEVELS[0])
    for one in old_arrows:
        assert all(board.grid[c[0]][c[1]] is not one for c in one.cells), \
            "重开后占用表里还留着旧箭头对象"
    assert not (old_ids & set(id(a) for a in board.arrows))
    for cell in old_nodes:
        assert board.cells[cell] is not old_nodes[cell], "旧格子节点还在邻居图里"
    assert len(board.cells) == sum(a.length for a in board.arrows)
    print("[5] 重新开始会重建全部箭头与邻居图，无旧引用残留  OK")

    # ---------- 6. 悬停不再泄漏"能不能飞" ----------
    board.load_level(LEVELS[1])
    flyable = _find_flyable(board)
    blocked = _find_blocked(board)
    assert flyable is not None and blocked is not None
    samples = []
    for one in (flyable, blocked):
        surf = pygame.Surface(WINDOW_SIZE)
        surf.fill((0, 0, 0))
        board.draw(surf, board.cell_rect(*one.cells[0]).center, False)
        outline = sum(_cell_lit(surf, COLOR_HOVER_OUTLINE,
                                board.cell_rect(r, c)) for (r, c) in one.cells)
        red = _color_count(surf, COLOR_BLOCKED)
        green = _color_count(surf, COLOR_DEBUG_FREE)
        assert red == 0, "悬停时出现了红色像素（%d），会泄漏能不能飞" % red
        assert green == 0, "悬停时出现了绿色像素（%d），会泄漏能不能飞" % green
        # 两支箭长度不同，所以按"每格多少个描边像素"来比较
        samples.append(outline / float(len(one.cells)))
    assert abs(samples[0] - samples[1]) < 1.0 and samples[0] > 50, \
        "能飞 / 被挡的悬停提示不一样（每格描边像素 %s），会泄漏答案" % (samples,)
    print("[6] 悬停只有中性描边（能飞与被挡的提示完全一样，无红绿预览）  OK")

    # ---------- 7. 状态机：开始 -> 游戏 ----------
    assert game.state == STATE_START
    game.process_frame([], 1.0 / 60.0)
    _click(game, game.scenes[STATE_START].main_button.rect.center)
    assert game.state == STATE_PLAYING, game.state
    assert game.scenes[STATE_PLAYING].mode == MODE_LEVEL
    assert game.scenes[STATE_PLAYING].level_index == 0
    print("[7] 首页「开始游戏」-> 关卡模式第 1 关  OK")

    scene = game.scenes[STATE_PLAYING]
    board = scene.board

    # ---------- 8. 有阻挡：本体冲过去撞一下再弹回 ----------
    probe = None
    for level in LEVELS:
        board.load_level(level)
        for one in board.arrows:
            if not board.can_fly(one) and board.travel_and_contact(one)[0] >= 1:
                probe = (level, list(one.cells), one.direction)
                break
        if probe is not None:
            break
    assert probe is not None, "所有关卡里都找不到「前面还有空隙」的被挡箭头"
    board.load_level(probe[0])
    blocked = None
    for one in board.arrows:
        if one.cells == probe[1] and one.direction == probe[2]:
            blocked = one

    travel, hit_cell = board.travel_and_contact(blocked)
    assert hit_cell is not None
    dr, dc = DIR_STEPS[blocked.direction]
    assert hit_cell == (blocked.head[0] + dr * (travel + 1),
                        blocked.head[1] + dc * (travel + 1)), "撞点算错了"
    assert board.grid[hit_cell[0]][hit_cell[1]] is not None, "撞点上没有箭"

    before = board.mistakes
    alive_before = board.remaining
    tail_cell = blocked.tail

    surf = pygame.Surface(WINDOW_SIZE)
    surf.fill((0, 0, 0))
    board.draw(surf, None, False)
    rest_lit = _cell_lit(surf, blocked.color, board.cell_rect(*tail_cell))
    assert rest_lit > 100, "基准像素太少（%d），这个检验没意义" % rest_lit

    assert board.handle_click(board.cell_rect(*blocked.cells[0]).center) == "blocked"
    assert board.remaining == alive_before and board.mistakes == before + 1
    assert blocked.anim is not None and not blocked.flying
    assert blocked in board.arrows, "弹回时本体应该还在棋盘上"

    while blocked.anim is not None and blocked.anim.time < blocked.anim.forward_time:
        board.update(1.0 / 60.0)
    assert blocked.offset > 0.5, "弹回动画里本体没有动（offset=%.2f）" % blocked.offset
    surf.fill((0, 0, 0))
    board.draw(surf, None, False)
    moved_lit = _cell_lit(surf, blocked.color, board.cell_rect(*tail_cell))
    assert moved_lit * 2 < rest_lit, \
        ("箭尾原来那格还剩 %d 像素的同色图形（静止时 %d）—— "
         "说明飞的是幻影、本体没动" % (moved_lit, rest_lit))

    box = board.board_rect().inflate(board.cell_size * 6, board.cell_size * 6)
    saw_overshoot = False
    steps = 0
    while blocked.anim is not None and steps < 240:
        steps += 1
        if blocked.offset < -0.05:
            saw_overshoot = True
        for point in board.arrow_points(blocked):
            assert box.collidepoint(point), \
                "弹回途中本体画到了离谱的位置 %s —— 轨道回卷了" % (point,)
        board.update(1.0 / 60.0)
    assert saw_overshoot, "弹回没有出现过冲，负位移这条路径没被覆盖到"
    assert blocked.anim is None and blocked.offset == 0.0, "弹回没有精确回到原位"
    assert blocked in board.arrows and board.grid[tail_cell[0]][tail_cell[1]] is blocked
    board.effects = []
    board.mistakes = before
    print("[8] 有阻挡 -> 本体挪出原格再弹回（原格像素 %d -> %d / %d）  OK"
          % (rest_lit, moved_lit, rest_lit))

    # ---------- 9. 无阻挡：本体飞出棋盘，飞完才回收 ----------
    flyable = _find_flyable(board)
    cells_before = len(board.cells)
    assert board.handle_click(board.cell_rect(*flyable.cells[0]).center) == "cleared"
    assert flyable.flying and flyable in board.arrows, "飞出去的应该是本体"
    assert board.remaining == alive_before - 1
    assert len(board.cells) == cells_before - flyable.length
    assert board.grid[flyable.tail[0]][flyable.tail[1]] is None
    assert not board.can_fly(flyable)
    for _ in range(60):
        board.update(1.0 / 60.0)
    assert flyable not in board.arrows, "飞完之后应该被回收"
    print("[9] 无阻挡 -> 本体（%d 格）沿自己的轨道飞出，飞完才回收  OK"
          % flyable.length)

    # ---------- 10. 关卡模式：逐关推进 -> 全部通关 ----------
    scene.mode = MODE_LEVEL
    scene.level_index = 0
    game.change_state(STATE_PLAYING)
    assert _clear_level(game, scene) == STATE_WIN
    for expect in (1, 2):
        win = game.scenes[STATE_WIN]
        assert win.buttons[0].text == "进入下一关"
        _click(game, win.buttons[0].rect.center)
        assert game.state == STATE_PLAYING
        assert scene.level_index == expect
        assert _clear_level(game, scene) == STATE_WIN
    print("[10] 关卡模式 第 1 -> 第 2 -> 第 3 关 逐关推进成功  OK")

    # ---------- 11. 全部通关 -> 解锁无尽模式（记录写入存档） ----------
    win = game.scenes[STATE_WIN]
    assert win.buttons[0].text == "进入无尽模式"
    assert game.records.levels_cleared == len(LEVELS)
    assert game.records.endless_unlocked
    assert os.path.isfile(save_path), "最佳记录没有落盘"
    reloaded = Records(save_path)
    assert reloaded.levels_cleared == len(LEVELS), "存档里的通关进度不对"
    print("[11] 三关全通 -> 解锁无尽模式，最佳记录已存盘  OK")

    # ---------- 12. 无尽模式：逐关推进；失败即整局结束 ----------
    _click(game, win.buttons[0].rect.center)
    assert game.state == STATE_PLAYING and scene.mode == MODE_ENDLESS
    assert scene.stage == 1 and scene.cleared == 0
    for expect in (1, 2):
        assert _clear_level(game, scene) == STATE_WIN
        assert scene.cleared == expect
        win = game.scenes[STATE_WIN]
        _click(game, win.buttons[0].rect.center)
        assert game.state == STATE_PLAYING and scene.stage == expect + 1
        assert scene.board.remaining > 0, "进入下一关后应该是全新的棋盘"
    assert game.records.endless == 2, "无尽模式成绩没记上：%s" % game.records.endless

    board = scene.board
    target = _find_blocked(board)
    board.mistakes = board.max_mistakes - 1
    board.handle_click(board.cell_rect(*target.cells[0]).center)
    scene.check_result()
    assert game.state == STATE_FAIL, game.state
    fail = game.scenes[STATE_FAIL]
    assert "本局结束" in fail.title, "无尽模式失败应该是整局结束，而不是普通失败"
    assert fail.buttons[0].text.startswith("再开一局"), \
        "无尽模式失败后只能开新的一局，不能从这一关重来"
    assert game.records.endless == 2
    _click(game, fail.buttons[0].rect.center)          # 再开一局
    assert game.state == STATE_PLAYING
    assert scene.stage == 1 and scene.cleared == 0, "新的一局必须从第 1 关开始"
    print("[12] 无尽模式失败 -> 整局结束（只能从第 1 关开新局），成绩已记录  OK")

    # ---------- 13. 速度模式：倒计时 / 失误扣时间 / 时间到结算 ----------
    game.start_speed()
    assert game.state == STATE_PLAYING and scene.mode == MODE_SPEED
    assert abs(scene.time_left - SPEED_SECONDS) < 1e-6
    assert scene.board.rows == 6 and scene.board.cols == 6

    # 失误一次 -> 扣时间
    target = _find_blocked(scene.board)
    t_before = scene.time_left
    _click(game, scene.board.cell_rect(*target.cells[0]).center)
    assert abs(scene.time_left - (t_before - SPEED_MISTAKE_PENALTY)) < 0.05, \
        "速度模式失误没有扣时间：%.2f -> %.2f" % (t_before, scene.time_left)

    # 通过一道 -> 立刻换下一道，计时不停
    guard = 0
    while scene.cleared == 0 and guard < 800 and scene.time_left > 0:
        guard += 1
        one = _find_flyable(scene.board)
        if one is not None:
            scene.board.handle_click(scene.board.cell_rect(*one.cells[0]).center)
        game.process_frame([], 1.0 / 60.0)
    assert scene.cleared == 1, "通过一道机关后计数没加"
    assert scene.stage == 2 and scene.board.remaining > 0, "没有换下一道机关"

    # 把时间推到 0 -> 结算 + 记录
    scene.time_left = 0.3
    while game.state == STATE_PLAYING and scene.time_left > 0:
        game.process_frame([], 1.0 / 60.0)
    game.process_frame([], 1.0 / 60.0)
    assert game.state == STATE_TIMEUP, game.state
    up = game.scenes[STATE_TIMEUP]
    assert up.buttons[0].text == "再来一次"
    assert game.records.speed == 1, "速度模式成绩没记上：%s" % game.records.speed
    reloaded = Records(save_path)
    assert reloaded.speed == 1 and reloaded.endless == 2, \
        "存档内容不对：endless=%s speed=%s" % (reloaded.endless, reloaded.speed)
    _click(game, up.buttons[0].rect.center)
    assert game.state == STATE_PLAYING
    assert SPEED_SECONDS - 0.1 < scene.time_left <= SPEED_SECONDS, \
        "再来一次没有重置计时：%.2f" % scene.time_left
    assert scene.cleared == 0 and scene.stage == 1
    print("[13] 速度模式：%d 秒倒计时、失误 -%d 秒、时间到结算并记录（最佳 %d 道）  OK"
          % (int(SPEED_SECONDS), int(SPEED_MISTAKE_PENALTY), game.records.speed))

    # ---------- 14. 首页显示最佳记录 ----------
    game.change_state(STATE_START)
    surf = pygame.Surface(WINDOW_SIZE)
    game.scenes[STATE_START].draw(surf)
    from_start = surf.copy()
    assert game.records.endless == 2 and game.records.speed == 1
    assert game.records.endless_unlocked
    game.process_frame([], 1.0 / 60.0)
    print("[14] 首页读取并显示最佳记录（无尽 %d 关 · 速度 %d 道）  OK"
          % (game.records.endless, game.records.speed))

    # ---------- 15. 提示：高亮出来的必须真的能飞 ----------
    scene.mode = MODE_LEVEL
    scene.level_index = 1
    scene.set_limits(*feature_limits(MODE_LEVEL))
    game.change_state(STATE_PLAYING)
    board = scene.board
    assert scene.hints_left is None, "关卡模式的提示应该不限次数"

    for _ in range(3):              # 先把局面弄乱一点
        one = _find_flyable(board)
        if one is not None:
            board.click_cell(one.cells[0][0], one.cells[0][1], False)
    for _ in range(6):
        assert scene.do_hint()
        hinted = board.hint_arrow
        assert hinted is not None and board.can_fly(hinted), \
            "提示高亮的必须是一支现在就能飞出去的箭"
        surf = pygame.Surface(WINDOW_SIZE)
        surf.fill((0, 0, 0))
        board.draw(surf, None, False)
        assert _color_count(surf, COLOR_HINT_MARK) > 100, "提示高亮没有画出来"
        board.hint_time = 0.01      # 让高亮到时间自己消失
        board.update(0.02)
        assert board.hint_arrow is None, "提示应该到时间就消失"
    print("[15] 提示：高亮的一定是「现在就能飞」的箭，且会自己消失  OK")

    # ---------- 16. 撤销：必须把整张邻居图一起还原 ----------
    scene.level_index = 1
    game.change_state(STATE_PLAYING)
    board = scene.board
    assert scene.history == []

    def signature(target):
        """把局面压成可比较的签名：每支箭的格子+朝向、失误、点击数、格子数。"""
        return (tuple(sorted((tuple(a.cells), a.direction)
                             for a in target.arrows if not a.flying)),
                target.mistakes, target.clicks, len(target.cells))

    initial = signature(board)

    free_one = _find_flyable(board)
    r0, c0 = free_one.cells[0]
    board.click_cell(r0, c0, False)
    scene.history.append((r0, c0, False))
    mid = signature(board)
    assert mid != initial

    blocked_one = _find_blocked(board)
    assert blocked_one is not None
    r1, c1 = blocked_one.cells[0]
    board.click_cell(r1, c1, False)          # 撞一下，失误 +1
    scene.history.append((r1, c1, True))
    assert board.mistakes == 1

    # 撤销一步 -> 回到一步之前，失误也要跟着回滚
    assert scene.do_undo()
    assert signature(board) == mid, "撤销一步之后局面和一步前不一致"
    assert board.mistakes == 0, "撞击那一次失误没有跟着撤销"
    ok, why = board.verify_neighbors()
    assert ok, why
    ok, why = board.verify_move_rule()
    assert ok, why

    # 再撤一步 -> 回到最初：飞走的那支箭必须回来，而且邻居图是重建出来的
    assert scene.do_undo()
    assert signature(board) == initial, "撤销到底之后没有回到最初那张图"
    ok, why = board.verify_neighbors()
    assert ok, why
    assert not scene.do_undo(), "没有历史了就不该还能撤销"

    # 对照：直接重新载入本关，签名必须和撤销结果一致
    board.load_level(LEVELS[1])
    assert signature(board) == initial, "撤销结果和重新载入的结果不一致"
    print("[16] 撤销：箭头回来 + 邻居图重建 + 失误回滚，与重新载入完全一致  OK")

    # ---------- 17. 无尽 / 速度模式：提示与撤销的次数限制 ----------
    game.start_endless()
    scene = game.scenes[STATE_PLAYING]
    assert (scene.hints_left, scene.undos_left) == (3, 3), \
        "无尽模式应该每局 3 次提示、3 次撤销"
    assert scene.can_hint() and not scene.can_undo()   # 还没点过，撤销无事可做
    for _ in range(3):
        assert scene.do_hint()
    assert scene.hints_left == 0 and not scene.do_hint(), "提示用完就不该再给"
    assert not scene.can_hint()

    for expect in (2, 1, 0):
        one = _find_flyable(scene.board)
        r, c = one.cells[0]
        scene.board.click_cell(r, c, False)
        scene.history.append((r, c, False))
        assert scene.do_undo()
        assert scene.undos_left == expect
    one = _find_flyable(scene.board)
    r, c = one.cells[0]
    scene.board.click_cell(r, c, False)
    scene.history.append((r, c, False))
    assert not scene.do_undo(), "撤销用完就不该还能撤销"

    game.start_speed()
    assert (scene.hints_left, scene.undos_left) == (2, 2), \
        "速度模式应该每局 2 次提示、2 次撤销"
    board = scene.board
    target = _find_blocked(board)
    assert target is not None
    before_t = scene.time_left
    _click(game, board.cell_rect(*target.cells[0]).center)
    assert scene.time_left < before_t, "速度模式撞击没有扣时间"
    assert scene.history[-1][2] is True
    assert scene.do_undo()
    assert abs(scene.time_left - before_t) < 0.05, "撤销撞击没有把扣掉的时间还回来"
    assert scene.undos_left == 1

    scene.mode = MODE_LEVEL
    scene.set_limits(*feature_limits(MODE_LEVEL))
    assert scene.hints_left is None and scene.undos_left is None
    print("[17] 次数限制：无尽 3/3、速度 2/2、关卡不限；撤销撞击会退还扣掉的时间  OK")

    # ---------- 18. 创意工坊：拓展功能可开关，开关会存盘 ----------
    records = game.records
    assert records.hint_on and records.undo_on, "两个拓展默认应该是开着的"
    scene.mode = MODE_LEVEL
    scene.level_index = 1
    scene.set_limits(*feature_limits(MODE_LEVEL))
    game.change_state(STATE_PLAYING)
    board = scene.board
    one = _find_flyable(board)
    r, c = one.cells[0]
    board.click_cell(r, c, False)
    scene.history.append((r, c, False))

    records.set_hint_on(False)              # 关掉提示
    assert not scene.can_hint() and not scene.do_hint()
    assert board.hint_arrow is None, "停用后不该还能提示"
    records.set_undo_on(False)              # 关掉撤销
    assert not scene.can_undo() and not scene.do_undo()
    assert len(scene.history) == 1, "被停用的撤销不该动到历史"

    records.set_hint_on(True)               # 再打开就又可用
    records.set_undo_on(True)
    assert scene.can_hint() and scene.do_hint()
    assert scene.can_undo() and scene.do_undo()
    assert scene.history == []

    records.set_hint_on(False)              # 开关要写进存档
    assert Records(save_path).hint_on is False, "拓展开关没有落盘"
    records.set_hint_on(True)
    assert Records(save_path).hint_on is True

    game.change_state(STATE_WORKSHOP)       # 工坊界面能画出来，且带着开关
    game.process_frame([], 1.0 / 60.0)
    workshop = game.scenes[STATE_WORKSHOP]
    assert len(workshop.cards) == 2, "功能页应该有两张卡片（提示 / 撤销）"
    assert all(toggle for _rect, _feature, toggle in workshop.cards)
    assert workshop.sound_toggle is not None
    print("[18] 创意工坊：提示/撤销可开关、停用后按键无效、开关写入存档  OK")

    # ---------- 19. 音效：两套音色、可开关、波形真的不一样 ----------
    assert game.sound.ok, "mixer 没起来，音效不可用"
    assert len(game.sound.sounds) == len(SOUND_STYLES) * len(SOUND_KINDS), \
        "每种音色都该有飞出/撞击两个音效"
    waves = {}
    peaks = {}
    for style in SOUND_STYLES:
        for kind in SOUND_KINDS:
            data = build_wave(style, kind)
            waves[(style, kind)] = data
            peaks[(style, kind)] = max(abs(v) for v in array.array("h", data))
            assert peaks[(style, kind)] > 1000, \
                "%s/%s 合成出来几乎是静音（峰值 %d）" % (
                    style, kind, peaks[(style, kind)])
    for style in SOUND_STYLES:
        ratio = peaks[(style, "hit")] / float(peaks[(style, "fly")])
        assert ratio >= SOUND_HIT_MIN_RATIO, \
            "%s 音色的撞击音不够响：撞击/飞出 = %.2f（要求 ≥ %.1f）" % (
                style, ratio, SOUND_HIT_MIN_RATIO)
    assert waves[("electronic", "fly")] != waves[("wood", "fly")], \
        "两套音色的飞出音不该是同一段波形"
    assert waves[("electronic", "hit")] != waves[("wood", "hit")], \
        "两套音色的撞击音不该是同一段波形"

    records = game.records
    records.set_sound_on(True)
    records.set_sound_style("electronic")
    assert game.play_sound("fly") and game.sound.last == ("electronic", "fly")
    assert game.play_sound("hit") and game.sound.last == ("electronic", "hit")
    records.set_sound_style("wood")
    assert game.play_sound("fly") and game.sound.last == ("wood", "fly"), \
        "换音色之后播的还是老音色"
    records.set_sound_on(False)
    assert not game.play_sound("fly"), "关掉音效之后不该还能出声"
    records.set_sound_on(True)

    # 真点一下也要出声（走的是游戏里的调用路径）
    scene.mode = MODE_LEVEL
    scene.level_index = 0
    game.change_state(STATE_PLAYING)
    played = []
    original_play = game.sound.play
    game.sound.play = lambda kind, style: (played.append((style, kind)),
                                           original_play(kind, style))[1]
    one = _find_blocked(scene.board)          # 先撞一下（这时还有被挡的箭）
    assert one is not None
    _click(game, scene.board.cell_rect(*one.cells[0]).center)
    one = _find_flyable(scene.board)          # 再点掉一支能飞的
    assert one is not None
    _click(game, scene.board.cell_rect(*one.cells[0]).center)
    game.sound.play = original_play
    assert ("wood", "fly") in played, "点掉一支能飞的箭没有播放飞出音效"
    assert ("wood", "hit") in played, "撞上阻挡没有播放碰撞音效"
    assert Records(save_path).sound_style == "wood", "音色选择没有落盘"
    print("[19] 音效：两套音色各两种音效、可切换可关闭，点击时真的会播  OK")

    # ---------- 20. 创意工坊的地图：解析 / 校验 / 可解性 / 坏文件不崩 ----------
    board = game.scenes[STATE_PLAYING].board
    level = normalize_level(EXAMPLE_MAP_DATA)
    assert level["rows"] == 6 and level["cols"] == 6
    board.load_level(level)
    assert len(board.arrows) == 7 and board.is_solvable(), "示例地图应该是 7 支且可解"

    # rows/cols 自动推算 + 折线方向自动取最后一段
    auto = normalize_level({"arrows": [
        {"row": 0, "col": 0, "length": 3, "direction": "right"},
        {"cells": [(1, 0), (2, 0), (2, 1)]},
    ]})
    assert auto["rows"] == 3 and auto["cols"] == 3, "rows/cols 没有自动推算"
    board.load_level(auto)
    assert board.arrows[1].direction == DIR_RIGHT, "折线方向没有取最后一段"

    # 格式层面的错误必须报 ValueError（工坊会把它显示在条目上，而不是崩）
    for why, raw in (
            ("顶层不是对象", [1, 2, 3]),
            ("一支箭头都没有", {"arrows": []}),
            ("方向不认识", {"arrows": [{"row": 0, "col": 0, "length": 2,
                                    "direction": "西北"}]}),
            ("简写缺方向", {"arrows": [{"row": 0, "col": 0, "length": 2}]}),
            ("格子是负数", {"arrows": [{"cells": [[-1, 0]]}]}),
            ("既没有 cells 也没有 row/col/length", {"arrows": [{"foo": 1}]}),
            ("棋盘太大", {"rows": 99, "cols": 99,
                      "arrows": [{"cells": [[0, 0]]}]}),
    ):
        try:
            normalize_level(raw)
        except ValueError:
            pass
        else:
            raise AssertionError("「%s」这种情况应该报 ValueError" % why)

    # 几何层面的错误交给 Board 报（同样是 ValueError）
    for why, raw in (
            ("越界", {"rows": 2, "cols": 2, "arrows": [
                {"row": 0, "col": 0, "length": 5, "direction": "right"}]}),
            ("两支箭重叠", {"rows": 3, "cols": 3, "arrows": [
                {"row": 0, "col": 0, "length": 3, "direction": "right"},
                {"row": 0, "col": 2, "length": 1, "direction": "right"}]}),
            ("箭身断开", {"rows": 3, "cols": 3, "arrows": [
                {"cells": [[0, 0], [2, 2]]}]}),
    ):
        try:
            board.load_level(normalize_level(raw))
        except ValueError:
            pass
        else:
            raise AssertionError("「%s」这种情况应该报 ValueError" % why)

    # 写文件 -> 扫目录 -> 读回来
    example_path = os.path.join(MAPS_DIR, EXAMPLE_MAP_FILE)
    write_example_map(example_path)
    assert os.path.isfile(example_path), "示例地图没有写出来"
    found = scan_maps(BOARD_AREA)
    assert EXAMPLE_MAP_FILE in [item["file"] for item in found]
    mine = [item for item in found if item["file"] == EXAMPLE_MAP_FILE][0]
    assert mine["level"] is not None and mine["solvable"] and mine["arrows"] == 7

    # 目录里丢一个坏文件，扫描要把它标成错误，而不是整个崩掉
    broken = os.path.join(MAPS_DIR, "_selftest_broken.json")
    with open(broken, "w", encoding="utf-8") as fp:
        fp.write("{ 这不是合法的 json")
    try:
        found = scan_maps(BOARD_AREA)
        bad = [item for item in found if item["file"] == "_selftest_broken.json"][0]
        assert bad["level"] is None and bad["error"], "坏文件没有被标成错误"
    finally:
        os.remove(broken)
    print("[20] 地图：示例可解、尺寸自动推算、格式/几何错误都报错、坏文件不崩  OK")

    # ---------- 21. 自定义地图模式：加载 / 通关 / 回工坊 ----------
    level = normalize_level(EXAMPLE_MAP_DATA)
    game.play_custom_map(level)
    scene = game.scenes[STATE_PLAYING]
    assert scene.mode == MODE_CUSTOM
    assert scene.hints_left is None and scene.undos_left is None, \
        "自定义地图不该限提示/撤销次数"
    assert scene.board.remaining == 7
    assert _clear_level(game, scene) == STATE_WIN
    win = game.scenes[STATE_WIN]
    assert win.buttons[1].text == "返回创意工坊"
    _click(game, win.buttons[1].rect.center)
    assert game.state == STATE_WORKSHOP, game.state

    # 自己试玩通关了 -> 盖上「已通关」，而且要落盘；改了地图就自动失效
    assert game.records.map_cleared(level), "通关后应该记上「已通关」"
    assert Records(save_path).map_cleared(level), "「已通关」标记没有落盘"
    edited = normalize_level(dict(EXAMPLE_MAP_DATA,
                                  arrows=EXAMPLE_MAP_DATA["arrows"][:-1]))
    assert not game.records.map_cleared(edited), \
        "改动过地图之后，「已通关」标记应该失效"

    # 工坊两个页签都能画出来，地图页也能列出地图
    workshop = game.scenes[STATE_WORKSHOP]
    assert len(workshop.tab_buttons) == 2
    for tab in ("feature", "map"):
        workshop.switch_tab(tab)
        game.process_frame([], 1.0 / 60.0)
    assert workshop.maps, "地图页应该能扫到示例地图"
    print("[21] 自定义地图：加载 7 支、提示/撤销不限、通关后盖「已通关」并能回工坊  OK")

    # ---------- 22. 文件完整性校验（hash） ----------
    manifest_path = os.path.join(_HERE, CHECKSUM_FILE)
    assert os.path.isfile(manifest_path), \
        "仓库里应该有 %s（跑 --hash-write 生成）" % CHECKSUM_FILE
    listed, listed_hash = read_checksums(manifest_path)
    assert listed and listed_hash, "清单应该能读出来并且带指纹"
    assert len(listed) >= 100, "清单至少要收录代码 + vendor 依赖，实际 %d 条" % len(listed)
    now_items, now_hash = build_manifest()
    assert now_hash == listed_hash, "当前代码的指纹应该和清单一致（改完代码要重跑 --hash-write）"
    good = verify_checksums(manifest_path)
    assert good["state"] == "ok", "当前仓库应该校验通过，实际是 %s" % describe_verify(good)
    assert not good["changed"] and not good["lost"] and not good["extra"]

    # 改一个字节就必须被发现；顺便验证"少一个文件""多一个文件"也能发现
    tmp_root = os.path.join(_HERE, "_selftest_hash")
    if os.path.isdir(tmp_root):
        shutil.rmtree(tmp_root)
    os.makedirs(tmp_root)
    try:
        shutil.copy2(os.path.join(_HERE, "arrow_puzzle.py"),
                     os.path.join(tmp_root, "arrow_puzzle.py"))
        tmp_manifest = os.path.join(tmp_root, CHECKSUM_FILE)
        write_checksums(tmp_manifest, root=tmp_root)
        assert verify_checksums(tmp_manifest, root=tmp_root)["state"] == "ok"
        with open(os.path.join(tmp_root, "arrow_puzzle.py"), "ab") as fp:
            fp.write(b"\n# tampered\n")             # 篡改一个字节
        tampered = verify_checksums(tmp_manifest, root=tmp_root)
        assert tampered["state"] == "bad", "改过文件之后必须报不一致"
        assert "arrow_puzzle.py" in tampered["changed"], tampered
        os.remove(os.path.join(tmp_root, "arrow_puzzle.py"))
        assert verify_checksums(tmp_manifest, root=tmp_root)["lost"], \
            "文件丢了也要能发现"
        # 没有清单时不能崩，只报告"无法比对"
        assert read_checksums(os.path.join(tmp_root, "没有这个文件.txt")) == (None, None)
        assert verify_checksums(os.path.join(tmp_root, "没有这个文件.txt"),
                                root=tmp_root)["state"] == "missing"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    print("[22] 文件完整性：清单 %d 条、指纹一致；改一字节/丢一个文件都能发现  OK"
          % len(listed))

    # ---------- 23. 远程清单校验 + 校验界面 ----------
    # 本地文件、远程文本走同一套解析：随便造一份清单也能解析
    sample = ("# 测试清单\n"
              "aaaa  arrow_puzzle.py\n"
              "bbbb  vendor/pygame/SDL2.dll\n"
              "# 指纹（以上清单整体的 SHA256）：ffff\n")
    parsed, parsed_hash = parse_checksums_text(sample)
    assert parsed == [("arrow_puzzle.py", "aaaa"),
                      ("vendor/pygame/SDL2.dll", "bbbb")], parsed
    assert parsed_hash == "ffff", parsed_hash

    # 拿一份"全对不上"的清单去比，三种情况都要能分出来（而且不抛异常）
    wrong = [("arrow_puzzle.py", "0" * 64), ("没有这个文件.py", "0" * 64)]
    mismatch = compare_manifest(wrong, "0" * 64)
    assert mismatch["state"] == "bad"
    assert mismatch["changed"] == ["arrow_puzzle.py"], mismatch["changed"]
    assert mismatch["lost"] == ["没有这个文件.py"], mismatch["lost"]
    assert "run_tests.py" in mismatch["extra"], "本地有、清单里没有的应算多余"

    # 连不上网时必须"报告失败"，而不是崩或者假装通过
    offline = verify_against_remote("http://127.0.0.1:1/CHECKSUMS.txt", timeout=2.0)
    assert offline["state"] == "offline", offline
    assert offline["error"], "离线也要给出原因"
    assert "联网校验失败" in describe_verify(offline)
    # 取回来不是清单（比如一个 HTML 页面）也要能识别
    bad_remote = compare_manifest([], None)
    bad_remote.update({"state": "badremote", "error": "没有可用的清单"})
    assert describe_verify(bad_remote) == "没有可用的清单"

    # 校验界面：本地校验能出结论，界面画得出来
    game.change_state(STATE_VERIFY)
    verify_scene = game.scenes[STATE_VERIFY]
    local = verify_scene.check_local()
    assert local["state"] == "ok", describe_verify(local)
    assert len(verify_scene.buttons) == 4
    assert "github.com" in REPO_URL and "CHECKSUMS.txt" in REPO_RAW_URL
    game.process_frame([], 1.0 / 60.0)
    print("[23] 远程校验：清单解析一致、离线报错不崩、%d 个文件本地校验通过、界面可绘制  OK"
          % local["checked"])

    # ---------- 24. 七个界面都能画出来 ----------
    for state in (STATE_START, STATE_PLAYING, STATE_WIN, STATE_FAIL,
                  STATE_TIMEUP, STATE_WORKSHOP, STATE_VERIFY):
        game.change_state(state, clicks=3, mistakes=1, has_next=True,
                          finished_all=False, mode=MODE_LEVEL, stage=1,
                          cleared=2, best=3, is_best=True, level_index=0)
        game.process_frame([], 1.0 / 60.0)
    print("[24] 七个界面绘制正常  OK")

    game.shutdown()
    if os.path.isfile(save_path):
        os.remove(save_path)
    print("\n自检通过：图形朝向、关卡数据、沿轨道移动、提示/撤销、创意工坊（功能+地图）、"
          "无尽/速度/自定义模式、最佳记录、文件完整性、状态机全部符合预期。")
    if report_path is not None:
        sys.stdout.flush()
    return 0


# ==========================================================================
# 十二、入口
# ==========================================================================
def print_hash_report():
    """`--hash`：把每个文件的校验码和整体指纹打出来，玩家可以直接看。"""
    items, fingerprint = build_manifest()
    for rel, value in items:
        print("%s  %s" % (value, rel))
    print("")
    print("收录文件数：%d" % len(items))
    print("整体指纹（%s）：%s" % (HASH_ALGO.upper(), fingerprint))
    return 0


def print_verify_report():
    """`--verify`：按 CHECKSUMS.txt 逐项核对，返回进程退出码。"""
    result = verify_checksums()
    if result["state"] == "missing":
        print("没有找到 %s，无法校验。" % CHECKSUM_FILE)
        print("（维护者可以跑 python arrow_puzzle.py --hash-write 生成清单）")
        return 2
    print("按 %s 逐项核对 %d 个文件……" % (CHECKSUM_FILE, result["checked"]))
    for label, key in (("改动", "changed"), ("丢失", "lost"), ("多余", "extra")):
        for rel in result[key]:
            print("  [%s] %s" % (label, rel))
    print("")
    print("本地指纹：%s" % result["fingerprint"])
    print("清单指纹：%s" % (result["expected"] or "（清单里没写指纹）"))
    if result["state"] == "ok":
        print("结论：一致，%d 个文件都没有被改动过。" % result["checked"])
        return 0
    print("结论：不一致 —— %s。" % describe_verify(result))
    return 1


def main():
    if "--selftest" in sys.argv:
        return run_selftest()

    if "--hash" in sys.argv:
        return print_hash_report()
    if "--hash-write" in sys.argv:
        info = write_checksums()
        print("已生成 %s" % info["path"])
        print("收录文件数：%d" % info["count"])
        print("整体指纹（%s）：%s" % (HASH_ALGO.upper(), info["fingerprint"]))
        return 0
    if "--verify" in sys.argv:
        return print_verify_report()

    level_index = 0
    if "--level" in sys.argv:
        level_index = int(sys.argv[sys.argv.index("--level") + 1])
        level_index = max(0, min(level_index, len(LEVELS) - 1))

    mode = MODE_LEVEL
    if "--endless" in sys.argv:
        mode = MODE_ENDLESS
    elif "--speed" in sys.argv:
        mode = MODE_SPEED

    game = Game(level_index, mode=mode)
    if mode == MODE_ENDLESS:
        game.start_endless()        # --endless 直接开一局（不受解锁限制）
    elif mode == MODE_SPEED:
        game.start_speed()
    game.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
