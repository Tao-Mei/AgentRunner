# Changelog / 更新记录

## 0.2.0-preview.2 — 2026-10-05

### English

Windows x64 preview, not a stable release.

- Live elapsed time in the job table and details; completed, failed and cancelled jobs retain their total duration. Duration counts wall time from execution start, including pauses, recovery waits and finalizers, excluding initial queue time.
- Human-readable durations (`1h 2m 3s`) and local creation dates instead of raw timestamp strings. Numeric sorting is preserved.
- Codex supplies a short task name and source-project note at submission. `run`, `exec` and `submit` accept `--name` and `--note`; older calls remain compatible.
- Edit names and notes directly in the table or details, with synchronized automatic saving. Refresh/sort/switch and save-failure protection retain drafts. Renaming changes display metadata only, not execution or callback identity.
- Details show a selectable task ID. Existing unnamed history remains unchanged until the user edits it.
- The app title, CLI `--version`, Windows file properties, installation registry and installer filename identify this preview version. Python uses the equivalent `0.2.0rc2`; Windows numeric version is `0.2.0.2`.

#### Installation and upgrade

Download `AgentRunner-Setup-0.2.0-preview.2.exe` from the Release Assets and run the wizard. Python and companion Codex Skills are included. Choose an installation folder and optional desktop shortcut, then launch from the Start menu or shortcut and select **Help**.

Resolve running jobs and callbacks before upgrading. Upgrades reuse the registered folder and preserve task data/settings. To move an installation, uninstall first, then reinstall in a new folder. The installer updates its owned global Skills. Reopen Codex and try a new chat if updated Skills are not recognized.

Codex chat integration requires the user's own configured Codex installation. AgentRunner does not manage Codex accounts or read/store Codex login credentials; the local Codex program handles authentication.

#### Validation and limits

The recent UI/metadata changes passed isolated source checks and successive upgrades on the development computer, preserving task metadata and settings. This release adds version consistency checks and Windows version resources. Final artifact checks and upgrade results are recorded in the GitHub Release notes. An earlier preview passed clean Windows VM checks without Python; these recent changes have not repeated full clean-VM or cross-project chat acceptance. Goal pause/restore uses an experimental local Codex protocol, requires user authorization, and uncertain state needs manual review.

### 简体中文

Windows x64 预览版，尚非稳定版。

- 列表和详情实时显示已运行时间，完成、失败及取消后固定显示总时长。从开始执行计算，包含暂停、恢复等待和收尾，不含启动前排队。
- 时长改为“1小时2分3秒”等可读形式，创建日期转换为本机当地时间；保留数值排序。
- Codex 提交时附上简短任务名称和来源项目备注。`run`、`exec`、`submit` 新增 `--name` 和 `--note`，兼容旧调用。
- 名称与备注可在列表和详情直接编辑，同步并自动保存；刷新、排序、切换及保存失败时保护未保存内容。改名只改变显示信息，不改变执行及回调关联。
- 详情直接显示可复制的任务编号。旧任务没有保存的名称不自动编造，用户可自行修改。
- 窗口标题、CLI `--version`、Windows 文件属性、安装登记及安装包文件名统一标识本版。Python 对应版本为 `0.2.0rc2`，Windows 数值版本为 `0.2.0.2`。

#### 安装与升级

在 Release 的 Assets 下载 `AgentRunner-Setup-0.2.0-preview.2.exe` 并运行向导，自带 Python 和 Codex 配套 Skill。选择安装位置及是否创建桌面快捷方式，完成后从开始菜单或快捷方式打开，点击“使用帮助”。

升级前请完成运行中的任务和待处理回调。升级沿用登记目录，保留任务数据及设置；迁移位置需先卸载再重新安装。安装器更新其拥有的全局 Skill；如果 Codex 未识别更新，重新打开 Codex 并尝试新建聊天。

Codex 聊天集成要求用户自行配置 Codex。AgentRunner 不管理 Codex 账号，不读取或保存其登录凭据；认证由本机 Codex 程序处理。

#### 验证范围与限制

最近界面和提交元数据更新已通过隔离源码测试及开发机连续覆盖升级，保留任务元数据和设置。本次增加版本一致性检查和 Windows 文件版本属性；最终安装包校验及升级结果记录在 GitHub 发布说明。早期预览包已通过无 Python 干净 Windows 虚拟机验证，本次未重复完整虚拟机及跨项目聊天验收。目标暂停/恢复依赖实验性 Codex 本地协议，需要用户授权；状态不明确时需人工核对。

## 0.2.0-preview.1 — 2026-10-03

### English

First public Windows desktop preview: bundled Python, task window and tray, installation folder selection, optional desktop shortcut, bilingual help, companion Skills, editable notes, clickable history locks, column reorder/sorting and conservative history cleanup.

### 简体中文

首次公开 Windows 桌面预览版：自带 Python、任务窗口与托盘、安装目录选择、可选桌面快捷方式、中英文帮助、配套 Skill、备注编辑、可点击历史锁、列拖动与排序，以及保守的历史清理。
