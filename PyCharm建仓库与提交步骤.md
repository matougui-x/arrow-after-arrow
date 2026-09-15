# 用 PyCharm 内置 Git 建仓库并提交（中文界面版，不需要另外装 Git）

> 你桌面上有 PyCharm 2026.2.1，而且装了中文语言包。**PyCharm 自带 Git**，所以不用装 git 也能建仓库、提交、推送到 GitHub/Gitee。
>
> 下面每个菜单都写成「**中文名（English）**」，因为不同汉化补丁的译法略有差别，找不到时就按括号里的英文找。
> 大概 10 分钟能做完。
>
> ⚠️ **新版界面（New UI）提示**：2026 版默认是新界面，**顶部菜单栏是藏起来的**，要点窗口**左上角的 ☰ 汉堡图标**才展开菜单（文件 / 编辑 / 视图 / … / Git）。
> 如果嫌找菜单麻烦，直接用 **`Ctrl+Shift+A`（查找操作 / Find Action）**，输入中文或英文关键字即可直达功能 —— 这条最稳，下面很多步都能用。

---

## 一、启用版本控制

1. **文件（File）→ 打开（Open）**，选中 `C:\Users\X\Desktop\作业\arrow_puzzle` 文件夹。
   * 注意是 **arrow_puzzle**，不是作业根目录；`Open Design` 那些不要带进来。
2. 展开 ☰ 菜单 → **VCS**（部分汉化把这一项译作「**版本控制**」）→ **启用版本控制集成…（Enable Version Control Integration…）**
   → 下拉选 **Git** → 确定（OK）。
   * 这一步只是把当前项目标记成 Git 仓库（相当于 `git init`），**不会动任何文件**。
   * 用 `Ctrl+Shift+A` 输入「启用版本控制集成」或 `Enable Version Control` 也能直接调到这个对话框。
3. **如果弹窗说找不到 Git**：☰ → **文件（File）→ 设置（Settings）**（快捷键 `Ctrl+Alt+S`）→ 左侧 **版本控制（Version Control）→ Git**
   → 右侧 **「Git 可执行文件路径（Path to Git executable）」** 点 **测试（Test）**，PyCharm 一般能自动找到自带的 git；
   找不到就点输入框右侧的下拉，里面通常有 **下载（Download）** 让它自己装一个。
4. 左侧 **项目（Project）** 面板里文件名会变**红色** —— 这表示"还没提交"，正常。

**先确认 `.gitignore` 已经在了**（我已经放在 `arrow_puzzle\.gitignore`），
它会让 `build/`、`build_tools/`、`save.json`、`__pycache__`、`_temp_exe/` 这些不进仓库。

> 想验证它生效：`Ctrl+Shift+A` → 输入 `gitignore`；或者打开「提交」对话框，看列表里有没有 `__pycache__`（**不该有**）。

---

## 二、分 6 次提交（路线 B：用「项目」面板右键添加，不用在提交列表里逐个点）

**核心技巧**：不要在提交窗口那个**扁平列表**里点（未进行版本管理的文件是平铺的，没有目录行）。
正确的做法是去左侧 **项目（Project）** 面板 —— 那里是**目录树** —— 右键 → **Git → 添加（Add）**，
把这一轮要交的文件先纳入版本控制；然后 `Ctrl+K`，提交窗口里就**只剩这一批**，直接提交即可。

### 每一轮的固定动作

1. `Alt+1` 切到**项目（Project）** 面板
2. 选中本轮要交的**文件或目录**（目录可以一次选中它下面全部文件）
3. **右键 → Git → 添加（Add）**（快捷键 `Ctrl+Alt+A`）
4. `Ctrl+K` 打开提交窗口 → 确认勾选的文件就是这一批 → 填提交信息 → 点 **提交（Commit）**
   * ⚠️ **「未进行版本管理的文件」那个节点必须保持不勾**（默认就是不勾的），否则会把后面几轮的东西一起交上去

### 6 轮的内容

| 轮次 | 提交信息（可直接抄） | 在项目面板里对哪些东西右键「Git → 添加」 |
| --- | --- | --- |
| 1 | `chore: 项目骨架（.gitignore / 依赖 / 内置 pygame）` | `.gitignore`、`requirements.txt`、**`vendor/` 目录** |
| 2 | `feat: 一箭又一箭主体（状态机 + 棋盘 + 沿轨道移动 + 创意工坊）` | `arrow_puzzle.py` |
| 3 | `test: 23 项自检 + T01~T09 验收用例` | `run_tests.py` |
| 4 | `build: 打包脚本与可执行文件` | `build_exe.py`、`dist/ArrowAfterArrow.zip` |
| 5 | `asset: 示例地图与界面截图` | `maps/` 目录、`docs/` 目录 |
| 6 | `docs: 说明文档、测试记录与作业博客` | `README.md`、`BLOG_测试记录.md`、`交作业版博客.md`、`博客补充材料.md`、`PyCharm建仓库与提交步骤.md` |

> **为什么第 2 条不能拆成"游戏主体"和"创意工坊"两条**：整个游戏是**一个文件** `arrow_puzzle.py`
> （3758 行），PyCharm 只能整文件提交、不支持按代码块分批暂存，硬拆就是假历史。
> 所以这里改成**按交付物类型**分（骨架 / 主体 / 测试 / 打包 / 素材 / 文档），每条都是真实存在的东西。
>
> 第 1 轮给 `vendor/` 建索引时 PyCharm 会卡几秒到十几秒（约 206 个文件），正常。

### 6 轮做完再一次性推送

`Ctrl+Shift+K` → 点 **定义远程（Define remote）** → 粘贴 GitHub 上的仓库地址 → **推送（Push）**。
这样只需要认证一次，远程上的历史也是完整的 6 条。

---

## 三、建远程仓库并推送

### 3.1 先在 GitHub（或 Gitee）网站上建空仓库

网站界面一般没有汉化，按英文找即可：

1. 登录 GitHub → 右上角 **+ → New repository（新建仓库）**
2. Repository name 填 `software-homework-2`（或 `arrow-after-arrow`，随意）
3. 选 **Public**（作业要能给助教看）
4. **不要勾** "Add a README file" / ".gitignore" / "license"（避免和本地冲突）
5. **Create repository**，然后复制页面上的 HTTPS 地址，形如
   `https://github.com/你的用户名/software-homework-2.git`

### 3.2 回到 PyCharm 推送

1. ☰ → **Git → 管理远程…（Manage Remotes…）**
2. 点 **+**，名称填 `origin`，URL 粘贴上面那个地址 → 确定
   * 或者直接 `Ctrl+Shift+K` 打开推送窗口，点里面的 **定义远程（Define remote）** 也行
3. `Ctrl+Shift+K`（或 ☰ → **Git → 推送…（Push…）**）→ 勾上 `main`（或 `master`）分支 → 点 **推送（Push）**
4. 第一次会要求登录 GitHub：PyCharm 会弹浏览器授权，按提示点 **Authorize** 即可
   （也可以改用**令牌（Token / Personal Access Token）**；Gitee 上用账号密码或私人令牌）

### 3.3 检查

打开网页版仓库，应该能看到：

* 文件列表里有 `arrow_puzzle.py`、`run_tests.py`、`build_exe.py`、`README.md`、`maps/`、`vendor/`
* 提交历史（Commits）里有 **6 条**提交
* 点进 `arrow_puzzle.py` 能正常显示（不是乱码）

**克隆验证**（作业里的加分项，也是我最推荐的一步）：
换台机器或换个空文件夹克隆一份，然后按 README 跑（**克隆出来的目录就是项目根目录，不用再 `cd` 子目录**）：

```bash
python arrow_puzzle.py            # 应该直接能玩（pygame 在 vendor/ 里，不用装）
python arrow_puzzle.py --selftest # 23 项自检全过
python run_tests.py               # T01~T09 全过
```

**本机没装 git 也能做这个验证**：PyCharm 欢迎界面（或 ☰ → **文件（File）→ 新建项目（New Project）**）
→ 左侧选 **来自版本控制（Get from VCS）** → 粘贴仓库地址 → 选一个空目录 → 克隆。
打开后 PyCharm 会让你选解释器（用你现有的 Python 3.7），然后直接运行 `arrow_puzzle.py` 即可。

---

## 四、仓库地址填哪儿

* `README.md` 顶部可以加一行仓库地址；
* 你博客「作业信息表」里的 `<仓库链接>` 和文末的仓库地址都要换成真实地址。

---

## 五、常见问题（中文界面）

| 现象 | 处理 |
| --- | --- |
| 文件名一直是红色、提交后没变绿 | 这些文件还在"未版本化（Unversioned）"里没被勾选，勾上后重新 **提交（Commit）** |
| 提交按钮是灰的 | 提交信息（Commit Message）是空的；另外确认至少勾选了一个文件 |
| 不小心把 `__pycache__` 提交了 | 先确认 `.gitignore` 生效；在项目面板右键该目录 → **Git → 删除…（Delete…）**，在弹窗里选择"从版本控制中删除但保留本地文件"，然后重新提交 |
| 推送报 443 / 认证失败 | 一般是网络或登录态问题；换 Gitee 步骤完全一样，网站换成 gitee.com 即可 |
| 找不到菜单 | 用 `Ctrl+Shift+A` 输关键字直达；或确认点的是左上角的 **☰** |
| 仓库太大（超过 100MB） | 主要是 `vendor/`（8MB）和 `dist/ArrowAfterArrow.zip`（8.9MB），都在限制内；不想传就在 `.gitignore` 里加上它们，但那样"克隆就能跑"就不成立了 |

---

## 六、中英对照速查表

| 中文界面 | 英文界面 | 快捷键 |
| --- | --- | --- |
| 文件 | File | — |
| 设置 | Settings | `Ctrl+Alt+S` |
| 查找操作 | Find Action | `Ctrl+Shift+A` |
| 项目（工具窗口） | Project | `Alt+1` |
| Git（工具窗口） | Git | `Alt+9` |
| 提交… | Commit… | `Ctrl+K` |
| 推送… | Push… | `Ctrl+Shift+K` |
| 更新项目 | Update Project | `Ctrl+T` |
| 管理远程… | Manage Remotes… | — |
| 定义远程 | Define remote | — |
| 启用版本控制集成… | Enable Version Control Integration… | — |
| 版本控制（设置页） | Version Control | — |
| Git 可执行文件路径 | Path to Git executable | — |
| 测试 / 下载（按钮） | Test / Download | — |
| 提交并推送 | Commit and Push | `Ctrl+Alt+K` |
| 回滚 | Rollback | `Ctrl+Alt+Z` |
| 显示差异 | Show Diff | `Ctrl+D` |
| 新建分支 | New Branch | `Ctrl+Alt+Shift+N` |
