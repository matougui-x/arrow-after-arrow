# 《一箭又一箭》测试记录：8 条验收用例，以及它们抓出来的 3 个 bug

> 项目：Python + Pygame 点击解谜小游戏《一箭又一箭》
> 本轮范围：验收清单 T01–T06，外加新增音效拓展的 T07–T09
> 环境：Windows / Python 3.7.0 / pygame 2.1.2（SDL 2.0.18）/ 无窗口 dummy 驱动 + dummy 音频驱动；
> 音效另在**真实显示与音频驱动**（`driver: windows`）上跑过一轮
> 复现命令：`python run_tests.py`（验收用例）、`python arrow_puzzle.py --selftest`（20 项内部自检）

---

## 一、这份记录想解决什么

这个小游戏前面的每一步改动，我都是靠"内部自检 + 截图肉眼看"来确认的。
自检有 20 项、覆盖得也算密，但它有个结构性问题：**它是开发者自己写的**，
断言的往往是我认为重要的东西，而不是验收清单上要求的东西。

所以这一轮做两件事：

1. 按验收清单**逐条驱动真实游戏对象**跑一遍（不是"看截图觉得对"）；
2. 把新增的音效拓展也纳入同一套用例。

结果比预期好——用例本身抓出了 3 个真 bug，其中 1 个是**直接段错误崩溃**级别的。

---

## 二、怎么测的

### 2.1 判定口径：什么叫"箭头消失了"

这个游戏里"消失"有两层含义，测的时候必须分清楚，不然会写出假阳性：

| 层 | 含义 | 判定依据 |
| --- | --- | --- |
| 逻辑层 | 它不再占格子、不再挡别人、计入"剩余箭头" | `board.grid` 里它的格子全变成 `None`；`remaining` 减 1；`board.cells`（邻居图）少掉它的格数 |
| 表现层 | 它作为对象都已经回收，不留残影 | 动画期间 `arrow.flying is True` 且对象仍在 `board.arrows`；动画结束后对象从 `board.arrows` 移除 |

T01 两条都断言了。只测第一条的话，"箭头飞出去了但对象没回收"这种泄漏是测不出来的。

### 2.2 测试手段

* **驱动真实对象**：用例直接 `import arrow_puzzle`，走 `Game` / `Board` / `PlayingScene`，
  点鼠标是真的 `pygame.event.Event(MOUSEBUTTONDOWN, ...)` 塞进主循环，
  按 R 是真的 `KEYDOWN`（T06）。不走 game 内部捷径，测的就是玩家走的路径。
* **无窗口无声音**：`SDL_VIDEODRIVER=dummy` + `SDL_AUDIODRIVER=dummy`，
  所以可以在命令行里反复跑、也能进 CI；mixer 拿不到真设备时会自动降级成静音，不影响判定。
* **不碰玩家存档**：用例用临时存档文件 `_unittest_save.json`，跑完删掉。
* **证据三层**：状态（`state == win`）+ 结构（格子/邻居图/计数）+ 数据（波形采样峰值）。

### 2.3 这轮的测试环境输出

```
========================================================================
《一箭又一箭》验收测试  T01 ~ T08
========================================================================
运行环境：Python 3.7.0 / pygame 2.1.2 / SDL 2.0.18
显示驱动：dummy　音频驱动：dummy（无声卡环境自动降级，不影响判定）
存档：临时文件 _unittest_save.json（不碰玩家的 save.json）
```

---

## 三、用例与结果汇总

```
编号    测试内容                           预期结果                       结论
T01   点击前方无阻挡的箭头                     箭头飞出棋盘并消失                  PASS
T02   点击前方有阻挡的箭头                     箭头不消失，失误次数减 1              PASS
T03   点击位于边缘且朝向棋盘外的箭头                箭头正常消失，不发生越界错误             PASS
T04   消除本关全部箭头                       显示通关并进入下一关                 PASS
T05   失误次数耗尽                         显示失败并允许重新开始                PASS
T06   游戏进行中重新开始                      箭头布局和失误次数恢复                PASS
T07   音效：飞出/碰撞各一组、两套音色               有飞出与碰撞音效，且至少两种可选           PASS
T08   音效开关与选择保存                      关掉后无声，选择写入存档               PASS
T09   音效适配不同 mixer 格式                有声卡的机器上也能正常出声              PASS

合计：9/9 通过
```

注意这是**修完 bug 之后**的结果。T03 第一次跑的时候不是 PASS，是直接崩了；
T09 是补测出来的用例，它对应的缺陷在真机上一跑就现形——见第五节。

---

## 四、逐条过程与实测数据

### T01 点击前方无阻挡的箭头

```
步骤：点击 Arrow(tail=(0, 4), len=2, dir=right)（2 格，朝向 右）
实测：返回 'cleared'；它占的格子 (0, 4)、(0, 5) 已全部清空；剩余箭头 6 -> 5；邻居图格子数 14 -> 12
      飞出动画期间 flying=True，动画结束后对象已回收=True
判定：PASS
```

邻居图格子数 14 → 12，正好等于这支箭的长度（2 格）——说明拆链是逐格做完的，
不是只把 `grid` 抹掉。动画期间 `flying=True` 且对象还在 `arrows` 里，
动画结束才回收，这正是"本体飞出去"的实现方式。

### T02 点击前方有阻挡的箭头

```
步骤：点击 Arrow(tail=(0, 0), len=3, dir=right)（朝向 右），前方 (0, 4) 处有箭挡着
实测：返回 'blocked'；箭头仍在原地（(0, 0)、(0, 1)、(0, 2)）；失误 0 -> 1；剩余箭头保持 6；产生了弹回动画=True
判定：PASS
```

除了"不消失 + 失误 +1"，还断言了它**三个格子一个都没少**、
`remaining` 不变、并且确实产生了弹回动画（否则就是"点了没反应"）。

### T03 点击位于边缘且朝向棋盘外的箭头

这条用例不是随便找一支箭，而是**遍历 3 个关卡筛出所有"箭头贴边且朝向棋盘外"的箭**——
这类箭最容易触发越界下标：

```
步骤：遍历 3 个关卡，找出所有「箭头贴边且朝向棋盘外」的箭，逐个点掉并跑完飞出动画（共 9 支）
      第 1 关 Arrow(tail=(0, 4), len=2, dir=right)：箭头格 (0, 5) 贴上边、朝向右 -> 'cleared'，剩余 6 -> 5，无异常=True
      第 2 关 Arrow(tail=(0, 4), len=2, dir=right)：箭头格 (0, 5) 贴上边、朝向右 -> 'cleared'，剩余 8 -> 7，无异常=True
      第 3 关 Arrow(tail=(7, 7), len=4, dir=right)：箭头格 (6, 7) 贴右边、朝向右 -> 'cleared'，剩余 13 -> 12，无异常=True
      第 3 关 Arrow(tail=(1, 2), len=3, dir=up)：箭头格 (0, 1) 贴上边、朝向上 -> 'cleared'，剩余 12 -> 11，无异常=True
      第 3 关 Arrow(tail=(7, 2), len=4, dir=left)：箭头格 (6, 0) 贴左边、朝向左 -> 'cleared'，剩余 11 -> 10，无异常=True
      第 3 关 Arrow(tail=(4, 5), len=3, dir=right)：箭头格 (4, 7) 贴右边、朝向右 -> 'cleared'，剩余 10 -> 9，无异常=True
      第 3 关 Arrow(tail=(3, 7), len=4, dir=up)：箭头格 (0, 7) 贴上边、朝向上 -> 'cleared'，剩余 9 -> 8，无异常=True
      第 3 关 Arrow(tail=(2, 0), len=3, dir=up)：箭头格 (0, 0) 贴上边、朝向上 -> 'cleared'，剩余 8 -> 7，无异常=True
      第 3 关 Arrow(tail=(4, 2), len=3, dir=left)：箭头格 (4, 0) 贴左边、朝向左 -> 'cleared'，剩余 7 -> 6，无异常=True
实测：全部正常飞出，未出现任何越界异常
判定：PASS
```

9 支覆盖了上/下/左/右四条边、直线箭头和折线箭头。**这条用例第一次跑的时候进程直接段错误崩了**，
细节见第五节 P1。

### T04 消除本关全部箭头

```
步骤：把第 1 关 6 支箭全部点掉 -> 在通关界面点「进入下一关」
实测：清空后状态 = state_win；通关界面主按钮 = 「进入下一关」；
      点它之后状态 = state_playing，当前关卡 = 第 2 关，新关卡箭头数 = 8
      共用了 6 次点击
判定：PASS
```

第 1 关理论最少 6 步，实测正好 6 次点击——没有多余操作，也没有卡关。

### T05 失误次数耗尽

```
步骤：把失误次数调到 2/3，再点一次被挡的箭头
实测：状态 = state_fail；失败界面按钮 = ['重新开始', '返回主菜单']；点「重新开始」后状态 = state_playing，失误 0/3，箭头数恢复为 6
      失败原因文案 = 「失误次数用完了，还有箭头没能飞出去」
判定：PASS
```

### T06 游戏进行中重新开始

```
步骤：先撞一次（把失误数弄脏）、再点掉一支能飞的，然后按 R
实测：重开前 剩余箭头=5 失误=1 点击=2 邻居图格子=12
      重开后 剩余箭头=6 失误=0 点击=0 邻居图格子=14
      与刚开始时的局面签名完全一致=True；邻居图自查=True
判定：PASS
```

这里用的"局面签名"是 `(每支箭的格子+朝向, 失误数, 点击数, 邻居图格子数)`。
和**开局时的签名**逐字节比较，再加上 `verify_neighbors()` 自查，
确保重开不是"看起来恢复了"，而是连邻居链表都重建成了初始状态。

### T07 音效：飞出/碰撞各一组、两套音色

音效不是外部素材文件，而是**用 `pygame.mixer` + 标准库 `array` 现场合成的波形**
（`build_wave()`），所以不依赖任何资源文件，拷到哪都能出声。

```
实测：mixer 可用=True；音效条目=[('electronic', 'fly'), ('electronic', 'hit'), ('wood', 'fly'), ('wood', 'hit')]
      采样峰值（越小越接近静音）：electronic/fly=13532、electronic/hit=15906、wood/fly=10813、wood/hit=14893
      两套音色的波形互不相同=True
      实际播放序列=[('electronic', 'hit'), ('electronic', 'fly'), ('wood', 'fly')]
判定：PASS
```

采样峰值这一列是防"合成了但其实是静音"——`int16` 满量程 32767，
四个音效峰值都在 1 万以上，确实有声音；两套音色的波形字节级不同，
换音色时播的确实是另一段。

### T08 音效开关与选择保存

```
实测：开启时播放=True；关闭时播放=False；重新读到的存档 sound_style='wood' sound_on=False
判定：PASS
```

关掉之后 `play_sound()` 直接返回 `False`，并且设置真的落到了 `save.json`（重新读文件核对过）。

### T09 音效适配不同 mixer 格式

这条是**补出来的**：把游戏放到真实音频驱动上跑了一次，发现音效是死的——
于是补了这条用例，专门模拟"真机上 mixer 已经被 `pygame.init()` 用默认参数开好"的情形。

```
步骤：分别用 44100/立体声、48000/立体声、22050/单声道 预先初始化 mixer
      （真机上 pygame.init() 就是这么干的），再构造 SoundKit 并播一次
      mixer 预设 (44100, -16, 2)    -> SoundKit 实际格式 (44100, -16, 2)    可用=True 条目=4 播放=True
      mixer 预设 (48000, -16, 2)    -> SoundKit 实际格式 (48000, -16, 2)    可用=True 条目=4 播放=True
      mixer 预设 (22050, -16, 1)    -> SoundKit 实际格式 (22050, -16, 1)    可用=True 条目=4 播放=True
实测：三种格式下 SoundKit 都能按 mixer 的真实声道数/采样率合成并播放
判定：PASS
```

修复前后在真机上的对照：

```
修复前  mixer format: (44100, -16, 2) | 音效可用: False
修复后  mixer format: (44100, -16, 2) | 音效可用: True | 格式: (44100, -16, 2) | 条目: 4
       播放飞出音效: True ('electronic', 'fly')
```

---

## 五、测试过程中发现并修复的问题

### P1（严重）连续开关多局游戏 → 段错误崩溃

**怎么发现的**：T03 要遍历 3 个关卡，所以它在一个进程里连续创建/销毁了 3 个 `Game`。
第一次执行到第 2 个 Game 时进程直接没了：

```
Fatal Python error: (pygame parachute) Segmentation Fault
Current thread (most recent call first):
  File "arrow_puzzle.py", line 545 in draw_text
  File "arrow_puzzle.py", line 2082 in draw_hud
  File "arrow_puzzle.py", line 2040 in draw
  File "arrow_puzzle.py", line 2413 in draw
  File "arrow_puzzle.py", line 2419 in process_frame
  File "run_tests.py", line 205 in t03
```

**根因**：字体对象是缓存在模块级的 `_FONT_CACHE` 里的：

```python
_FONT_CACHE = {}

def get_font(size, bold=False):
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]      # ← 复用了上一局游戏创建的 Font
    ...
```

`Game.shutdown()` 会调 `pygame.quit()`，那之后所有 `pygame.font.Font` 对象都失效了。
第二次 `Game.__init__` 里虽然又 `pygame.init()`，但缓存里还是**上一轮那些已经失效的 Font 对象**，
`font.render()` 直接踩内存 → 段错误。

正常玩不会遇到（一个进程只开一局），但只要有人写自动化、或者以后加"返回主菜单后重开一局"的就崩。
这是个典型的"测试逼出来的真 bug"。

**修复**：加 `clear_font_cache()`，`Game.__init__`（重新 init 之后）和 `Game.shutdown()`（quit 之前）各清一次。

```python
def clear_font_cache():
    """丢掉缓存的字体对象。

    pygame.quit() 之后旧的 Font 对象就不能再用了 —— 再用会直接段错误崩掉。
    所以 Game 初始化时清一次、退出时也清一次，
    这样同一个进程里连续开关多局游戏（自动化测试就是这么干的）才不会炸。
    """
    _FONT_CACHE.clear()
```

**回归**：修完之后 T03 从"崩溃"变成 PASS（9 支边缘箭全部正常飞出），
其余 7 条用例和 20 项自检也全绿。

### P2（严重）音效在任何有声卡的机器上都是哑的

**怎么发现的**：不是在 dummy 环境里发现的——dummy 环境下音效一切正常、T07/T08 都 PASS。
是我按惯例把游戏**放到真实驱动上跑了一遍**：

```
driver: windows | mixer: (44100, -16, 2)
real-window run OK (音效可用=False)
```

`mixer` 明明起来了，但 `SoundKit.ok` 是 `False`，也就是音效被静默丢弃了。
换句话说：**这个功能在有声卡的机器上一次都不会响**，而所有自动化测试都是绿的。

**根因**：`pygame.init()` 在有音频设备时会**先用默认参数把 mixer 开好**（这里是 44100/-16/**2 声道**），
而 `pygame.mixer.init()` 对已经初始化的 mixer 是**空操作**：

```python
pygame.mixer.init(frequency=SOUND_RATE, size=-16, channels=1, buffer=512)
# ↑ 无声地什么也没做，mixer 仍然是 2 声道
```

我却按**单声道**去合成 PCM 数据，`pygame.mixer.Sound(buffer=...)` 拿到长度不匹配的 buffer
直接抛错，被 `except (pygame.error, ValueError)` 吞掉，于是 `ok = False`、静音运行。

**修复**：不要假设格式，**先读回 mixer 的真实格式再按那个格式合成**；
位深不对时先 `quit()` 再重开：

```python
info = pygame.mixer.get_init()
if info is not None and info[1] != -16:
    pygame.mixer.quit()
    info = None
if info is None:
    pygame.mixer.init(frequency=SOUND_RATE, size=-16, channels=1, buffer=512)
info = pygame.mixer.get_init()
if info is None or info[1] != -16:
    return                      # 真的没有音频设备，静音运行
self.format = info
rate, _size, channels = info
...build_wave(style, kind, rate, channels)   # 多声道就把采样点重复几遍
```

**回归**：真机上 `音效可用=True`、4 个音效、播放返回 `True`；
并新增 **T09** 把"预设 44100/立体声、48000/立体声、22050/单声道"三种情形钉进用例里。

**教训**：`try/except` 把初始化错误吞掉的写法，最容易制造"测试全绿但功能全死"。
如果当时加一句"无声卡时降级"以外的日志或者断言，第一轮就能发现。

### P3（中）类的成员被放错了类

写这一轮的代码时，我用"替换一段文本"的方式往文件里插 `SoundKit`，
结果 `Records` 后半截成员（`endless_unlocked`、`bump_endless`、`bump_speed`、
`mark_levels_cleared`）被留在了新插入的 `SoundKit` 类体里面——Python 语法上完全合法，不会报任何错。

是自检跑起来才暴露的：`AttributeError: 'Records' object has no attribute 'endless_unlocked'`。
修法是把这 4 个成员挪回 `Records`。

**教训**：这种"语法合法、语义错位"的问题，静态阅读很难发现，
但只要有测试真的去调这些方法，一秒就露馅。

### P4（低）`draw_text()` 少了 `midleft` 参数

工坊音效卡片要用"左中对齐"画"已开启 / 已关闭"，调用时报
`TypeError: draw_text() got an unexpected keyword argument 'midleft'`。
补上 `midleft` 分支即可。

### P5 测试脚本自身的四个问题（这部分也值得记）

写完用例第一条就翻车，而且三次翻车都是**测试的错，不是产品的错**：

| 现象 | 原因 | 修法 |
| --- | --- | --- |
| T04 报 `IndexError: list index out of range`（通关界面没有按钮） | 我的循环在最后一支箭飞出的**缓冲期**（0.55s）结束前就退出了，没等到 `win_ready`，所以状态还停在 playing | 改成"只要还在 playing 就继续跑帧"，让缓冲期走完 |
| T06 报 `AttributeError: 'NoneType' object has no attribute 'cells'` | 第 1 关只有一支被挡的箭，我先点掉了它的阻挡者，之后"被挡的箭"就不存在了 | 调换顺序：先撞、再飞 |
| T07 播放序列是空的，看起来像"音效没生效" | 我直接调了 `board.click_cell()`，绕过了场景的事件处理——而音效是在事件处理里播的（撤销重放走同一个函数，**故意**不发声） | 改用真实鼠标事件驱动 |
| T04 打印"共用了 0 次点击" | 我在点了「进入下一关」之后才读 `board.clicks`，那时已经重载关卡、计数被清零了 | 在点下一关之前先取值 |

第三条特别值得记：如果当时偷懒直接改断言，就会得出"音效没问题"的结论，
而实际上我压根没测到播放路径。**测试也要被测试**——用真实入口、按真实顺序。

---

## 六、自动化测不到、靠人工核对的部分

* **界面排版**：工坊的音效卡片、开关状态、四个底部按钮的灰显/次数、提示高亮、无尽模式"本局结束"界面，
  都是把画面截出来一张张看的（自动化只保证"能画出来不报错"）。
  可参考 `docs/workshop_sound.png`：音效卡片里"木质"是选中态（蓝），"电子"是未选态（灰），
  开关是绿色胶囊，说明设置项和状态是联动的。

  ![创意工坊（含音效卡片）](docs/workshop_sound.png)

* **音色好不好听**：结论是"能出声、能换、能关"，但**听感**还是要人耳确认。
  这一轮先在 dummy 音频驱动下验证了"mixer 起来了 / 波形不是静音 / 换音色播的确实是另一段 /
  事件能触发播放"，然后放到真机（`driver: windows`）上验证了"格式适配 + 真的能播"——
  而正是这最后一步真机验证，抓到了 P2 那个"所有自动化都绿、功能却是死的"缺陷。
  剩下的（两套音色顺不顺耳、音量是否合适）仍然需要戴耳机听，如实记在这里。

* **手感**：飞出/弹回动画的节奏（0.15~0.30s 冲撞、0.44s 阻尼弹回）好不好，
  只能靠人玩；自动化只保证了动画会播完并被回收（自检第 8/14 项）。

---

## 七、打包成 exe 之后再验一遍

代码改完就"能跑"不等于"发出去的 exe 能跑"。打包用的是 PyInstaller
（`python build_exe.py`，产物 `dist/ArrowAfterArrow/`），打完做了两步验证：

**Step 1：让 exe 自己跑一遍全部 22 项自检。**

`--windowed` 的 exe 没有控制台，`print` 会被丢掉，所以给 `run_selftest()` 加了一条：
检测到 `sys.stdout is None` 就把 stdout/stderr 重定向到 exe 旁边的
`selftest_report.txt`。这样打包产物也能留下可查的证据：

```
[19] 音效：两套音色各两种音效、可切换可关闭，点击时真的会播  OK
[20] 地图：示例可解、尺寸自动推算、格式/几何错误都报错、坏文件不崩  OK
[21] 自定义地图：加载 7 支、提示/撤销不限、通关后盖「已通关」并能回工坊  OK
[22] 六个界面绘制正常  OK
自检通过：图形朝向、关卡数据、沿轨道移动、提示/撤销、创意工坊（功能+地图）、
无尽/速度/自定义模式、最佳记录、状态机全部符合预期。
```

进程退出码 **0**。

**Step 2：冒烟测一次真正的游戏启动。**

```
启动 6 秒后进程还在跑 = True
```

（窗口正常打开、主循环在转，然后手动关掉。）

### P6（严重，打包踩的坑）onefile 在受限环境下起不来

第一版我打的是 `--onefile`，结果 exe 一运行就卡住十分钟。原因是 onefile 的引导程序
每次启动都要先把 pygame/SDL 解包到系统临时目录，而这个环境不允许写那里：

```
Failed to extract SDL2.dll: failed to open target file!
fopen: Permission denied
```

`--windowed` 模式下这个错误还会以弹窗形式出现，看起来就跟死机一样。
把 `TEMP` 指到可写目录也没用。最后改成 **`--onedir`**（exe + 依赖同目录）：

* 启动时不解包，直接加载同目录的 dll → 启动更快，也不挑临时目录权限；
* 代价是发出去的是一个文件夹而不是单个文件（压缩一下 19.7 MB）。
* `build_exe.py --onefile` 仍然保留，在 `%TEMP%` 可写的普通机器上没问题。

**教训**：这类"打包后才暴露"的问题，只有真的把产物跑起来才会发现——
和 P2 一样，属于"源码层面怎么测都测不出来"的那一类。

---

## 八、明确没覆盖到的

* 长时间连续游玩的内存/句柄增长（只测了单局、T03 的连续 3 局、以及打包后跑一遍自检）。
* 存档被外部改坏的各种极端情况（现在只做了 `try/except`，测过"文件不存在"和正常读写）。
* 不同分辨率 / DPI 缩放下的界面（写死 1000x600）。
* 多显示器、全屏、真实音频设备中断等环境相关场景。
* 无尽模式和速度模式的完整通关（只测了状态流转与计数，没有"玩到 50 关"的压力测试）。
* exe 在**没有 Python 的干净机器**上运行（本机验证时环境里是有 Python 的；
  不过 PyInstaller 已经把 python37.dll 和全部依赖打进包里了）。

---

## 九、结论

1. **9 条验收用例全部通过**（T01–T06 按清单，T07–T09 覆盖新增音效），
   另有 20 项内部自检作为回归护栏，`python run_tests.py` 与
   `python arrow_puzzle.py --selftest` 都可一键复现。
2. 用例确实抓到了产品缺陷，而且**两条严重缺陷的发现路径完全不同**：
   * P1（段错误）是**自动化用例**跑出来的——日常手玩永远碰不到；
   * P2（音效静音）是**真机运行**跑出来的——自动化环境反而完全正常。
   所以"自动化 + 真机手动"两条腿都得有，缺哪条都会漏。
3. 四次测试脚本自身的错误提醒了一件事：**断言失败时先怀疑测试**。
   尤其是"绕过真实入口去调内部方法"这种写法，很容易测出一个假的通过，
   也容易测出一个假的失败。
4. 留了两个诚实的空白：**音效听感**和**长时间运行稳定性**，需要人耳和长时间环境补测。

---

## 附：本轮新增的音效拓展（技术说明）

音效做成创意工坊里的一个**可开关、可选音色**的拓展项：

* 波形现场合成，不依赖素材文件：

```python
def build_wave(style, kind, rate=SOUND_RATE):
    """现场合成一小段 16 位单声道 PCM（不依赖任何素材文件）。"""
    spec = SOUND_SPECS[(style, kind)]      # f0/f1/dur/vol/shape/decay
    ...
    return samples.tobytes()

self.sounds[(style, kind)] = pygame.mixer.Sound(buffer=build_wave(style, kind))
```

* 两套音色：`electronic 电子`（飞出=上滑方波、撞击=下坠锯齿）、
  `wood 木质`（飞出=清脆正弦"叮"、撞击=低沉的"咚"）；
* 玩家在工坊里选，选完立刻试听；开关与选择都写进 `save.json`；
* mixer 拿不到设备时自动降级静音，不影响游戏；
* 播放点在场景的事件处理里（`Game.play_sound()`），
  所以**撤销重放不会出声**——重放走的是 `Board.click_cell(animate=False)`。
