# -*- coding: utf-8 -*-
"""把《一箭又一箭》打包成可执行文件。

用法：
    python build_exe.py              # 默认 onedir：dist/ArrowAfterArrow/ArrowAfterArrow.exe
    python build_exe.py --onefile    # 打成单文件 exe（见下面的说明）

它做三件事：
    1. 确认 PyInstaller 可用（没有就 pip 装到项目内的 build_tools/，不动系统环境）
    2. 打包 arrow_puzzle.py，并把 vendor/ 里的 pygame 一起打进去
    3. 把 maps/ 里的地图复制到 exe 旁边，让工坊一打开就能看到地图

【为什么默认 onedir 而不是 onefile】
    onefile 的引导程序每次启动都要把 pygame/SDL 解包到系统临时目录再运行：
    · 启动慢一拍，且某些受限环境（没有写临时目录权限、杀软拦截）会直接失败
      —— 实测报错是 "Failed to extract SDL2.dll: fopen: Permission denied"；
    · onedir 直接在自己目录里加载 dll，启动快、没有解包这一步，最稳。
    想要单个文件就加 --onefile，在正常机器上没问题（前提是 %TEMP% 可写）。

【产物说明】
    双击 exe 即玩。存档 save.json 和 maps/ 都在 **exe 旁边**（不是解包临时目录），
    所以整个文件夹拷走，进度和地图都跟着走。
    游戏不依赖任何素材文件（字体走系统、音效是现场合成的波形、地图是纯文本），
    所以这里不需要 --add-data，包体只有 pygame 那一坨。
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "ArrowAfterArrow"
TOOLS = os.path.join(HERE, "build_tools")
DIST = os.path.join(HERE, "dist")
BUILD = os.path.join(HERE, "build")
PYINSTALLER_PIN = "pyinstaller==5.13.2"

# 这些库本机装了也用不上，排掉能让包小一圈
EXCLUDES = ("numpy", "scipy", "pandas", "matplotlib", "PIL", "tkinter",
            "PyQt5", "pytest", "IPython", "notebook")


def ensure_pyinstaller():
    """确保能 import PyInstaller；没有就装到项目内的 build_tools/。"""
    for path in (None, TOOLS):
        if path is not None:
            if not os.path.isdir(path):
                continue
            if path not in sys.path:
                sys.path.insert(0, path)
        try:
            import PyInstaller  # noqa: F401
            return True
        except ImportError:
            continue

    print("没找到 PyInstaller，装到 %s ..." % TOOLS)
    code = subprocess.call([sys.executable, "-m", "pip", "install",
                            "--target", TOOLS, PYINSTALLER_PIN])
    if code != 0:
        return False
    sys.path.insert(0, TOOLS)
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        return False


def build(onefile=False, console=False):
    if not ensure_pyinstaller():
        print("PyInstaller 不可用。可以手动装： python -m pip install pyinstaller")
        return 1
    from PyInstaller.__main__ import run as pyinstaller_run

    args = [
        os.path.join(HERE, "arrow_puzzle.py"),
        "--name", APP_NAME,
        "--onefile" if onefile else "--onedir",
        "--console" if console else "--windowed",
        "--noconfirm",
        "--clean",
        "--distpath", DIST,
        "--workpath", BUILD,
        "--specpath", BUILD,
        "--paths", os.path.join(HERE, "vendor"),   # 让分析器找到内置的 pygame
    ]
    for module in EXCLUDES:
        args += ["--exclude-module", module]

    print("开始打包（%s，第一次会慢一点）..." % ("onefile" if onefile else "onedir"))
    pyinstaller_run(args)

    # exe 的位置：onefile 直接在 dist/，onedir 在 dist/ArrowAfterArrow/
    app_dir = DIST if onefile else os.path.join(DIST, APP_NAME)
    exe = os.path.join(app_dir, APP_NAME + ".exe")
    if not os.path.isfile(exe):
        print("打包失败：没生成 %s" % exe)
        return 1

    # 让 exe 旁边就有一份示例地图
    maps_src = os.path.join(HERE, "maps")
    maps_dst = os.path.join(app_dir, "maps")
    if os.path.isdir(maps_src):
        if not os.path.isdir(maps_dst):
            os.makedirs(maps_dst)
        for name in sorted(os.listdir(maps_src)):
            if name.lower().endswith(".json"):
                shutil.copy2(os.path.join(maps_src, name),
                             os.path.join(maps_dst, name))
                print("  带上地图：%s" % name)

    print("完成：%s" % exe)
    if not onefile:
        total = sum(os.path.getsize(os.path.join(root, name))
                    for root, _dirs, files in os.walk(app_dir)
                    for name in files)
        print("  整个文件夹 %.1f MB（分发时把 %s 打包发出去就行）"
              % (total / 1048576.0, APP_NAME))
    else:
        print("  %.1f MB" % (os.path.getsize(exe) / 1048576.0))
    print("双击就能玩；save.json 和 maps/ 会生成在 exe 旁边。")
    return 0


def main():
    onefile = "--onefile" in sys.argv
    console = "--console" in sys.argv
    return build(onefile=onefile, console=console)


if __name__ == "__main__":
    sys.exit(main())
