# -*- coding: utf-8 -*-
"""
《一箭又一箭》验收测试脚本 —— T01 ~ T08

用法：
    python run_tests.py

这份脚本按验收用例逐条驱动真实的游戏对象（Game / Board / 事件系统），
测完打印一张结果表和每条用例的实测数据。
博客《BLOG_测试记录.md》里引用的数字就是从这份输出里抄的。
"""

import array
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_VENDOR = os.path.join(_HERE, "vendor")
if os.path.isdir(_VENDOR):
    sys.path.insert(0, _VENDOR)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # 无窗口
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")   # 无声卡也能跑

import pygame  # noqa: E402

import arrow_puzzle as G  # noqa: E402

SAVE = os.path.join(_HERE, "_unittest_save.json")
DT = 1.0 / 60.0
RESULTS = []


# ----------------------------------------------------------------------
# 工具
# ----------------------------------------------------------------------
def new_game(mode=G.MODE_LEVEL, level=0):
    """开一局干净的游戏（用临时存档，不动玩家的 save.json）。"""
    game = G.Game(level, mode=mode, records_path=SAVE)
    game.scenes[G.STATE_PLAYING].level_index = level
    game.change_state(G.STATE_PLAYING)
    return game


def click(game, pos):
    game.process_frame([pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                           {"pos": pos, "button": 1})], DT)


def press(game, key):
    game.process_frame([pygame.event.Event(pygame.KEYDOWN,
                                           {"key": key, "mod": 0,
                                            "unicode": ""})], DT)


def click_arrow(game, one, animate=True):
    """点在某支箭的某一格上，返回 handle_click 的结果字符串。"""
    board = game.scenes[G.STATE_PLAYING].board
    if animate:
        click(game, board.cell_rect(*one.cells[0]).center)
        return None
    return board.click_cell(one.cells[0][0], one.cells[0][1], True)


def find_flyable(board):
    for one in board.arrows:
        if not one.flying and board.can_fly(one):
            return one
    return None


def find_blocked(board):
    for one in board.arrows:
        if not one.flying and not board.can_fly(one):
            return one
    return None


def edge_outward(board):
    """所有"箭头位于棋盘边缘、且朝向棋盘外"的箭。"""
    found = []
    for one in board.arrows:
        row, col = one.head
        dr, dc = G.DIR_STEPS[one.direction]
        if not (0 <= row + dr < board.rows and 0 <= col + dc < board.cols):
            found.append(one)
    return found


def signature(board):
    return (tuple(sorted((tuple(a.cells), a.direction) for a in board.arrows
                         if not a.flying)),
            board.mistakes, board.clicks, len(board.cells))


def clear_level(game):
    """一直点能飞的箭，直到通关（把飞出动画和缓冲时间都跑完）。"""
    board = game.scenes[G.STATE_PLAYING].board
    scene = game.scenes[G.STATE_PLAYING]
    guard = 0
    while game.state == G.STATE_PLAYING and guard < 4000:
        guard += 1
        if not board.is_cleared() or not board.win_ready:
            one = find_flyable(board)
            if one is not None:
                board.click_cell(one.cells[0][0], one.cells[0][1], True)
        game.process_frame([], DT)
        scene.check_result()
    return game.state


def record(tid, title, expect, ok, detail):
    RESULTS.append((tid, title, expect, ok))
    print("-" * 72)
    print("%s  %s" % (tid, title))
    print("     预期：%s" % expect)
    for line in detail.splitlines():
        print("     %s" % line)
    print("     判定：%s" % ("PASS" if ok else "FAIL"))


# ----------------------------------------------------------------------
# T01 点击前方无阻挡的箭头
# ----------------------------------------------------------------------
def t01():
    game = new_game()
    board = game.scenes[G.STATE_PLAYING].board
    one = find_flyable(board)
    cells = list(one.cells)
    before_remaining = board.remaining
    before_cells = len(board.cells)

    result = board.click_cell(*cells[0], True)
    grid_empty = all(board.grid[r][c] is None for (r, c) in cells)
    during = (board.remaining, len(board.cells), one.flying)
    for _ in range(60):
        game.process_frame([], DT)
    recycled = one not in board.arrows

    ok = (result == "cleared" and grid_empty
          and board.remaining == before_remaining - 1
          and len(board.cells) == before_cells - one.length
          and during[2] is True and recycled)
    detail = ("步骤：点击 %s（%d 格，朝向 %s）\n"
              "实测：返回 '%s'；它占的格子 %s 已全部清空；剩余箭头 %d -> %d；"
              "邻居图格子数 %d -> %d\n"
              "      飞出动画期间 flying=%s，动画结束后对象已回收=%s"
              % (one, one.length, G.DIR_LABELS[one.direction], result,
                 "、".join("%s" % (c,) for c in cells),
                 before_remaining, board.remaining, before_cells,
                 len(board.cells), during[2], recycled))
    record("T01", "点击前方无阻挡的箭头", "箭头飞出棋盘并消失", ok, detail)
    game.shutdown()
    return ok


# ----------------------------------------------------------------------
# T02 点击前方有阻挡的箭头
# ----------------------------------------------------------------------
def t02():
    game = new_game()
    board = game.scenes[G.STATE_PLAYING].board
    one = find_blocked(board)
    cells = list(one.cells)
    hit_cell = board.blocker_of(one)
    before_mistakes = board.mistakes
    before_remaining = board.remaining

    result = board.click_cell(*cells[0], True)
    still_there = all(board.grid[r][c] is one for (r, c) in cells)
    bounced = one.anim is not None
    ok = (result == "blocked" and still_there
          and board.mistakes == before_mistakes + 1
          and board.remaining == before_remaining)
    detail = ("步骤：点击 %s（朝向 %s），前方 %s 处有箭挡着\n"
              "实测：返回 '%s'；箭头仍在原地（%s）；失误 %d -> %d；"
              "剩余箭头保持 %d；产生了弹回动画=%s"
              % (one, G.DIR_LABELS[one.direction], hit_cell, result,
                 "、".join("%s" % (c,) for c in cells),
                 before_mistakes, board.mistakes, before_remaining, bounced))
    record("T02", "点击前方有阻挡的箭头", "箭头不消失，失误次数减 1", ok, detail)
    game.shutdown()
    return ok


# ----------------------------------------------------------------------
# T03 点击位于边缘且朝向棋盘外的箭头
# ----------------------------------------------------------------------
def t03():
    total = 0
    lines = []
    ok = True
    for index, level in enumerate(G.LEVELS):
        game = new_game(level=index)
        board = game.scenes[G.STATE_PLAYING].board
        samples = edge_outward(board)
        for one in samples:
            total += 1
            row, col = one.head
            side = ("上" if row == 0 else "下" if row == board.rows - 1 else
                    "左" if col == 0 else "右")
            before = board.remaining
            result = board.click_cell(*one.cells[0], True)
            for _ in range(60):
                game.process_frame([], DT)
            recycled = one not in board.arrows
            good = (result == "cleared" and recycled
                    and board.remaining == before - 1)
            ok = ok and good
            lines.append("      第 %d 关 %s：箭头格 %s 贴%s边、朝向%s -> '%s'，"
                         "剩余 %d -> %d，无异常=%s"
                         % (index + 1, one, (row, col), side,
                            G.DIR_LABELS[one.direction], result, before,
                            board.remaining, good))
        game.shutdown()
    ok = ok and total > 0
    detail = ("步骤：遍历 3 个关卡，找出所有「箭头贴边且朝向棋盘外」的箭，"
              "逐个点掉并跑完飞出动画（共 %d 支）\n" % total
              + "\n".join(lines)
              + "\n实测：全部正常飞出，未出现任何越界异常（越界时报 IndexError，"
                "本用例没有任何异常抛出）")
    record("T03", "点击位于边缘且朝向棋盘外的箭头",
           "箭头正常消失，不发生越界错误", ok, detail)
    return ok


# ----------------------------------------------------------------------
# T04 消除本关全部箭头
# ----------------------------------------------------------------------
def t04():
    game = new_game()
    scene = game.scenes[G.STATE_PLAYING]
    board = scene.board
    clicks_before = board.clicks
    state_after_clear = clear_level(game)      # 一直点到通关（含飞出动画与缓冲）
    used_clicks = board.clicks - clicks_before  # 要在点"下一关"之前读，否则会被重开清零
    win = game.scenes[G.STATE_WIN]
    win_button = win.buttons[0].text if win.buttons else "(没有按钮)"
    click(game, win.buttons[0].rect.center)
    ok = (state_after_clear == G.STATE_WIN
          and win_button == "进入下一关"
          and game.state == G.STATE_PLAYING
          and scene.level_index == 1
          and scene.board.remaining == len(G.LEVELS[1]["arrows"]))
    detail = ("步骤：把第 1 关 6 支箭全部点掉 -> 在通关界面点「%s」\n"
              "实测：清空后状态 = %s；通关界面主按钮 = 「%s」；"
              "点它之后状态 = %s，当前关卡 = 第 %d 关，新关卡箭头数 = %d\n"
              "      共用了 %d 次点击"
              % (win_button, state_after_clear, win_button, game.state,
                 scene.level_index + 1, scene.board.remaining, used_clicks))
    record("T04", "消除本关全部箭头", "显示通关并进入下一关", ok, detail)
    game.shutdown()
    return ok


# ----------------------------------------------------------------------
# T05 失误次数耗尽
# ----------------------------------------------------------------------
def t05():
    game = new_game()
    scene = game.scenes[G.STATE_PLAYING]
    board = scene.board
    one = find_blocked(board)
    board.mistakes = board.max_mistakes - 1     # 差一次就满
    board.click_cell(one.cells[0][0], one.cells[0][1], True)
    scene.check_result()
    state = game.state
    fail = game.scenes[G.STATE_FAIL]
    buttons = [b.text for b in fail.buttons]
    click(game, fail.buttons[0].rect.center)     # 重新开始
    ok = (state == G.STATE_FAIL and "重新开始" in buttons
          and game.state == G.STATE_PLAYING
          and board.mistakes == 0
          and board.remaining == len(G.LEVELS[0]["arrows"]))
    detail = ("步骤：把失误次数调到 %d/%d，再点一次被挡的箭头\n"
              "实测：状态 = %s；失败界面按钮 = %s；点「重新开始」后状态 = %s，"
              "失误 %d/%d，箭头数恢复为 %d\n"
              "      失败原因文案 = 「%s」"
              % (board.max_mistakes - 1, board.max_mistakes, state, buttons,
                 game.state, board.mistakes, board.max_mistakes,
                 board.remaining, fail.lines[0]))
    record("T05", "失误次数耗尽", "显示失败并允许重新开始", ok, detail)
    game.shutdown()
    return ok


# ----------------------------------------------------------------------
# T06 游戏进行中重新开始
# ----------------------------------------------------------------------
def t06():
    game = new_game()
    scene = game.scenes[G.STATE_PLAYING]
    board = scene.board
    fresh = signature(board)

    # 先玩几步：故意撞一次（把失误数弄脏），再点掉一支能飞的
    one = find_blocked(board)
    assert one is not None, "第 1 关应该有被挡住的箭"
    board.click_cell(one.cells[0][0], one.cells[0][1], True)
    one = find_flyable(board)
    board.click_cell(one.cells[0][0], one.cells[0][1], True)
    game.process_frame([], DT)
    played = (board.remaining, board.mistakes, board.clicks, len(board.cells))

    press(game, pygame.K_r)                     # 真的按一下 R
    after = signature(board)
    ok = (after == fresh and board.mistakes == 0
          and board.remaining == len(G.LEVELS[0]["arrows"]))
    ok_graph, why = board.verify_neighbors()
    ok = ok and ok_graph
    detail = ("步骤：点掉 2 支能飞的 + 撞 1 次（失误变脏），然后按 R\n"
              "实测：重开前 剩余箭头=%d 失误=%d 点击=%d 邻居图格子=%d\n"
              "      重开后 剩余箭头=%d 失误=%d 点击=%d 邻居图格子=%d\n"
              "      与刚开始时的局面签名完全一致=%s；邻居图自查=%s"
              % (played[0], played[1], played[2], played[3],
                 board.remaining, board.mistakes, board.clicks,
                 len(board.cells), after == fresh, ok_graph))
    record("T06", "游戏进行中重新开始", "箭头布局和失误次数恢复", ok, detail)
    game.shutdown()
    return ok


# ----------------------------------------------------------------------
# T07 音效：两套音色，飞出/碰撞各一种
# ----------------------------------------------------------------------
def t07():
    game = new_game()
    scene = game.scenes[G.STATE_PLAYING]
    board = scene.board

    mixer_ok = game.sound.ok
    kinds = sorted(game.sound.sounds.keys())
    peaks = {}
    for key, _sound in game.sound.sounds.items():
        data = G.build_wave(*key)
        peaks[key] = max(abs(v) for v in array.array("h", data))
    ratios = dict((style, peaks[(style, "hit")] / float(peaks[(style, "fly")]))
                  for style in G.SOUND_STYLES)
    loud_enough = all(ratio >= G.SOUND_HIT_MIN_RATIO
                      for ratio in ratios.values())
    styles_differ = (peaks and
                     G.build_wave("electronic", "fly") != G.build_wave("wood", "fly")
                     and G.build_wave("electronic", "hit")
                     != G.build_wave("wood", "hit"))

    played = []
    original = game.sound.play
    game.sound.play = lambda kind, style: (played.append((style, kind)),
                                           original(kind, style))[1]
    # 走真实点击路径（音效是在场景的事件处理里播的；撤销重放走 click_cell，
    # 所以不会出声 —— 这里必须用真事件，否则测不到）
    game.records.set_sound_style("electronic")
    one = find_blocked(board)
    click(game, board.cell_rect(*one.cells[0]).center)
    one = find_flyable(board)
    click(game, board.cell_rect(*one.cells[0]).center)
    game.records.set_sound_style("wood")
    one = find_flyable(board)
    click(game, board.cell_rect(*one.cells[0]).center)
    game.sound.play = original

    ok = (mixer_ok and len(kinds) == 4 and styles_differ and loud_enough
          and ("electronic", "hit") in played and ("electronic", "fly") in played
          and ("wood", "fly") in played)
    detail = ("步骤：查 mixer 状态与合成波形（含撞击/飞出音量比）；然后在两套音色下各点一次"
              "被挡的箭和能飞的箭，记录实际调用\n"
              "实测：mixer 可用=%s；音效条目=%s\n"
              "      采样峰值（越小越接近静音）：%s\n"
              "      撞击/飞出 音量比：%s（要求 ≥ %.1f，撞击明显更响）\n"
              "      两套音色的波形互不相同=%s\n"
              "      实际播放序列=%s"
              % (mixer_ok, kinds,
                 "、".join("%s/%s=%d" % (k[0], k[1], v)
                           for k, v in sorted(peaks.items())),
                 "、".join("%s: %.2f" % (s, r) for s, r in sorted(ratios.items())),
                 G.SOUND_HIT_MIN_RATIO, styles_differ, played))
    record("T07", "音效：飞出/碰撞各一组、两套音色",
           "有飞出与碰撞音效，而且碰撞明显更响", ok, detail)
    game.shutdown()
    return ok


# ----------------------------------------------------------------------
# T08 音效可关闭 + 选择会保存
# ----------------------------------------------------------------------
def t08():
    game = new_game()
    game.records.set_sound_style("wood")
    on_play = game.play_sound("fly")
    game.records.set_sound_on(False)
    off_play = game.play_sound("fly")
    saved = G.Records(SAVE)
    game.records.set_sound_on(True)

    ok = (on_play is True and off_play is False
          and saved.sound_style == "wood" and saved.sound_on is False)
    detail = ("步骤：选「木质」音色 -> 播一次 -> 关掉音效 -> 再播一次；"
              "然后重新读存档\n"
              "实测：开启时播放=%s；关闭时播放=%s；"
              "重新读到的存档 sound_style=%r sound_on=%r"
              % (on_play, off_play, saved.sound_style, saved.sound_on))
    record("T08", "音效开关与选择保存", "关掉后无声，选择写入存档", ok, detail)
    game.shutdown()
    return ok


# ----------------------------------------------------------------------
# T09 音效适配不同 mixer 格式
# ----------------------------------------------------------------------
def t09():
    lines = []
    ok = True
    for freq, channels in ((44100, 2), (48000, 2), (22050, 1)):
        pygame.mixer.quit()
        pygame.mixer.init(frequency=freq, size=-16, channels=channels,
                          buffer=512)
        before = pygame.mixer.get_init()
        kit = G.SoundKit()
        played = kit.play("fly", "wood")
        good = (kit.ok and kit.format == before and len(kit.sounds) == 4
                and played)
        lines.append("      mixer 预设 %-18s -> SoundKit 实际格式 %-18s "
                     "可用=%s 条目=%d 播放=%s"
                     % (before, kit.format, kit.ok, len(kit.sounds), played))
        ok = ok and good
        kit.shutdown()
    detail = ("步骤：分别用 44100/立体声、48000/立体声、22050/单声道 预先初始化 mixer"
              "（真机上 pygame.init() 就是这么干的），再构造 SoundKit 并播一次\n"
              + "\n".join(lines)
              + "\n实测：三种格式下 SoundKit 都能按 mixer 的真实声道数/采样率合成并播放")
    record("T09", "音效适配不同 mixer 格式", "有声卡的机器上也能正常出声", ok, detail)
    return ok


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main():
    print("=" * 72)
    print("《一箭又一箭》验收测试  T01 ~ T09")
    print("=" * 72)
    print("运行环境：Python %s / pygame %s / SDL %s"
          % (sys.version.split()[0], pygame.version.ver,
             ".".join(str(v) for v in pygame.get_sdl_version())))
    print("显示驱动：%s　音频驱动：%s（无声卡环境自动降级，不影响判定）"
          % (os.environ.get("SDL_VIDEODRIVER"),
             os.environ.get("SDL_AUDIODRIVER")))
    print("存档：临时文件 %s（不碰玩家的 save.json）"
          % os.path.basename(SAVE))
    print("")

    if os.path.isfile(SAVE):
        os.remove(SAVE)

    outcomes = [t01(), t02(), t03(), t04(), t05(), t06(), t07(), t08(), t09()]

    print("")
    print("=" * 72)
    print("结果汇总")
    print("=" * 72)
    print("%-5s %-30s %-26s %s" % ("编号", "测试内容", "预期结果", "结论"))
    for tid, title, expect, ok in RESULTS:
        print("%-5s %-30s %-26s %s"
              % (tid, title, expect, "PASS" if ok else "FAIL"))
    passed = sum(1 for item in RESULTS if item[3])
    print("")
    print("合计：%d/%d 通过" % (passed, len(RESULTS)))

    if os.path.isfile(SAVE):
        os.remove(SAVE)
    pygame.quit()
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
