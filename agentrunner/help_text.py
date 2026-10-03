"""Short user-facing desktop help, bundled for offline use."""

HELP = {
    'zh': '''AgentRunner 使用帮助

1. 如何开始
在 Codex 聊天中调用 $agent-runner，描述任务、工作目录和预期结果。Runner 独立执行，Codex 不必等待；任务结束后会向原聊天回调。程序窗口本身不是 Codex 提问聊天框。

2. 任务列表
左侧包含运行中和历史任务，点击任务查看右侧详情。单条命令的“步骤”页可能为空，日志在“输出”页。进度只展示可确认的事实，不预测剩余时间。
拖动表头可调整列顺序；点击表头切换升序或降序。列顺序和排序会保存。

3. 控制任务
“取消任务”请求终止任务；“暂停后续步骤”只阻止新步骤开始，正在运行的步骤继续；“恢复步骤调度”继续执行；“当前步骤结束后停止”等待当前步骤完成，再运行收尾步骤。

4. 提问、锁定和备注
选择常见问题或输入自定义问题后点击“询问 Agent”，会将一次任务快照发送到原 Codex 聊天。入队成功不代表已经回复，Runner 继续执行。
点击最左侧 L 列的开锁或闭锁图标，可切换任务是否保留；鼠标指向表头会显示“锁定/解锁”。备注默认为空，双击列表备注单元格即可输入，也可在右侧详情直接输入；两处同步并自动保存。保留锁不影响执行，也不同于执行资源锁。

5. 一键清理
清理已完成、失败或取消且未锁定的任务及 Runner 日志。回调尚未确认、目标恢复未结束或资源未释放的任务会保留。实际工作目录及产物不删除，必要的回调去重记录保留。清理后的日志和备注无法从窗口恢复，请先保存需要的内容。

6. 关闭和退出
关闭窗口不取消任务。勾选“点击关闭时收起到托盘”后，关闭会隐藏窗口，托盘“打开界面”可恢复。托盘“退出”只在任务和回调不再需要处理时退出程序。安装或升级会提供全局 Skill；自定义安装目录通过用户安装登记发现。
''',
    'en': '''AgentRunner help

1. Start a task
Invoke $agent-runner in a Codex chat and describe the task, working directory and expected result. Runner executes independently and sends completion back to that chat. This window is a task viewer, not a general Codex chat box.

2. Jobs
The left list includes running jobs and history. Select a job to inspect details. A single command may have no Steps; its logs appear under Output. Progress shows known facts, not a predicted finish time.
Drag column headers to reorder them; click a header to toggle ascending and descending order. Display preferences are saved.

3. Controls
Cancel requests termination. Pause next steps prevents new steps starting; active steps continue. Resume steps continues scheduling. Stop after current steps lets active steps finish, then runs finalizers.

4. Questions, locks and notes
Choose a quick question or enter your own, then click Ask Agent. A single task snapshot is queued in the original Codex chat. Queue acceptance does not mean an answer has arrived; Runner keeps executing.
Click the open or closed lock icon in the leftmost L column to protect history from cleanup. Hover over L for the Lock / unlock tooltip. Notes start empty: double-click a Note cell or type in the details note field. Both edit the same note and save automatically. History locks do not pause jobs or reserve execution resources.

5. Clean history
Cleanup removes unlocked completed, failed and cancelled jobs and Runner logs only after callbacks, goal recovery and resource leases are resolved. Working directories and artifacts are untouched. Callback deduplication records remain. Removed logs and notes cannot be recovered in this window; save anything needed first.

6. Close and exit
Closing the window does not cancel work. Close window to tray hides it; Open window restores it. Tray Exit refuses while work or callbacks still need attention. Installation includes global Skills; a custom install location is discovered through the current user's installation registry.
''',
}
