Unicode true
!include "MUI2.nsh"
!include "nsDialogs.nsh"

!ifndef ROOT
  !error "Pass /DROOT=... to makensis"
!endif
!ifndef STAGE
  !error "Pass /DSTAGE=... to makensis"
!endif
!ifndef OUT
  !error "Pass /DOUT=... to makensis"
!endif

!ifndef VERSION
  !error "Pass /DVERSION=... to makensis"
!endif
!ifndef WINVERSION
  !error "Pass /DWINVERSION=... to makensis"
!endif
Name "AgentRunner ${VERSION}"
VIProductVersion "${WINVERSION}"
VIAddVersionKey /LANG=1033 "ProductName" "AgentRunner"
VIAddVersionKey /LANG=1033 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "FileVersion" "${WINVERSION}"
VIAddVersionKey /LANG=1033 "FileDescription" "AgentRunner installer"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Tao Mei"
OutFile "${OUT}\AgentRunner-Setup-${VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\AgentRunner"
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show

!define MUI_ABORTWARNING
!define MUI_ICON "${ROOT}\agentrunner\assets\agentrunner.ico"
!define MUI_UNICON "${ROOT}\agentrunner\assets\agentrunner.ico"
!define MUI_LANGDLL_REGISTRY_ROOT "HKCU"
!define MUI_LANGDLL_REGISTRY_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner"
!define MUI_LANGDLL_REGISTRY_VALUENAME "InstallerLanguage"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${ROOT}\LICENSE"
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE ValidateDirectory
!insertmacro MUI_PAGE_DIRECTORY
Page custom ShortcutPage ShortcutLeave
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\AgentRunner.exe"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "SimpChinese"

LangString SubmitConflict ${LANG_ENGLISH} "An existing agent-runner Skill is not owned by this installer. Resolve that name conflict before installing."
LangString SubmitConflict ${LANG_SIMPCHINESE} "已有的 agent-runner Skill 不属于此安装器。请先处理同名 Skill 冲突，再安装。"
LangString CallbackConflict ${LANG_ENGLISH} "An existing agent-runner-callback Skill is not owned by this installer. Resolve that name conflict before installing."
LangString CallbackConflict ${LANG_SIMPCHINESE} "已有的 agent-runner-callback Skill 不属于此安装器。请先处理同名 Skill 冲突，再安装。"
LangString UpgradeBlocked ${LANG_ENGLISH} "AgentRunner still has active or unresolved work. Finish or inspect those jobs before upgrading."
LangString UpgradeBlocked ${LANG_SIMPCHINESE} "仍有正在运行或待核对的任务。请先完成或核对这些任务，再升级。"
LangString InstallProcesses ${LANG_ENGLISH} "Close AgentRunner and wait for all installed Runner processes to exit before installing or upgrading."
LangString InstallProcesses ${LANG_SIMPCHINESE} "请关闭 AgentRunner，并等待安装版相关进程全部退出，再安装或升级。"
LangString UninstallBlocked ${LANG_ENGLISH} "AgentRunner still has active or unresolved work. Finish or inspect those jobs before uninstalling."
LangString UninstallBlocked ${LANG_SIMPCHINESE} "仍有正在运行或待核对的任务。请先完成或核对这些任务，再卸载。"
LangString UninstallProcesses ${LANG_ENGLISH} "Close AgentRunner and wait for installed Runner processes to exit before uninstalling."
LangString UninstallProcesses ${LANG_SIMPCHINESE} "请关闭 AgentRunner，并等待安装版相关进程全部退出，再卸载。"
LangString DataPreserved ${LANG_ENGLISH} "Job data in the user's .agentrunner directory was preserved."
LangString DataPreserved ${LANG_SIMPCHINESE} "用户 .agentrunner 目录中的任务数据已保留。"
LangString ShortcutTitle ${LANG_ENGLISH} "Shortcuts"
LangString ShortcutTitle ${LANG_SIMPCHINESE} "快捷方式"
LangString ShortcutDescription ${LANG_ENGLISH} "Choose how to find AgentRunner after installation."
LangString ShortcutDescription ${LANG_SIMPCHINESE} "选择安装后如何找到 AgentRunner。"
LangString DesktopOption ${LANG_ENGLISH} "Create a desktop shortcut"
LangString DesktopOption ${LANG_SIMPCHINESE} "创建桌面快捷方式"
LangString MoveInstall ${LANG_ENGLISH} "To move an existing installation, uninstall it first and then install in the new folder. Job data and settings are preserved."
LangString MoveInstall ${LANG_SIMPCHINESE} "如需迁移现有安装，请先卸载，再选择新目录安装。任务数据与界面设置会保留。"
LangString EmptyFolder ${LANG_ENGLISH} "Choose an empty folder dedicated to AgentRunner."
LangString EmptyFolder ${LANG_SIMPCHINESE} "请选择专用于 AgentRunner 的空文件夹。"

Var ShortcutCheckbox
Var DesktopShortcut
Var PreviousInstall
Var RunnerDataRoot

Function .onInit
  !insertmacro MUI_LANGDLL_DISPLAY
  StrCpy $DesktopShortcut ${BST_CHECKED}
  ReadRegStr $PreviousInstall HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "InstallLocation"
  StrCmp $PreviousInstall "" 0 CheckPrevious
  IfFileExists "$LOCALAPPDATA\Programs\AgentRunner\runner.exe" 0 CheckPrevious
    StrCpy $PreviousInstall "$LOCALAPPDATA\Programs\AgentRunner"
  CheckPrevious:
  StrCmp $PreviousInstall "" InitDone
  IfFileExists "$PreviousInstall\runner.exe" 0 MissingPrevious
    StrCpy $INSTDIR $PreviousInstall
    Goto InitDone
  MissingPrevious:
    StrCpy $PreviousInstall ""
  InitDone:
FunctionEnd

Function ValidateDirectory
  StrCmp $PreviousInstall "" DirectoryValid
  StrCmp $INSTDIR $PreviousInstall DirectoryValid
  MessageBox MB_ICONSTOP "$(MoveInstall)"
  Abort
  DirectoryValid:
FunctionEnd

Function ShortcutPage
  !insertmacro MUI_HEADER_TEXT "$(ShortcutTitle)" "$(ShortcutDescription)"
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${NSD_CreateCheckbox} 0 10u 100% 18u "$(DesktopOption)"
  Pop $ShortcutCheckbox
  ${NSD_SetState} $ShortcutCheckbox $DesktopShortcut
  nsDialogs::Show
FunctionEnd

Function ShortcutLeave
  ${NSD_GetState} $ShortcutCheckbox $DesktopShortcut
FunctionEnd

Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd

Section "AgentRunner" MainSection
  SetShellVarContext current
  ReadEnvStr $RunnerDataRoot "AGENTRUNNER_HOME"
  StrCmp $RunnerDataRoot "" 0 +2
    StrCpy $RunnerDataRoot "$PROFILE\.agentrunner"
  Call ValidateDirectory
  IfFileExists "$PROFILE\.codex\skills\agent-runner\SKILL.md" 0 CheckCallbackCollision
  IfFileExists "$PROFILE\.codex\skills\agent-runner\.agentrunner-owned" CheckCallbackCollision 0
  MessageBox MB_ICONSTOP "$(SubmitConflict)"
  Abort
  CheckCallbackCollision:
  IfFileExists "$PROFILE\.codex\skills\agent-runner-callback\SKILL.md" 0 CheckInstalledService
  IfFileExists "$PROFILE\.codex\skills\agent-runner-callback\.agentrunner-owned" CheckInstalledService 0
  MessageBox MB_ICONSTOP "$(CallbackConflict)"
  Abort
  CheckInstalledService:
  IfFileExists "$INSTDIR\runner.exe" 0 CheckInstallProcesses
    ExecWait '"$INSTDIR\runner.exe" service-stop' $0
    StrCmp $0 "0" CheckInstallProcesses
    MessageBox MB_ICONSTOP "$(UpgradeBlocked)"
    Abort
  CheckInstallProcesses:
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /oname=install-preflight.ps1 "${ROOT}\packaging\install-preflight.ps1"
  ExecWait 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\install-preflight.ps1" -InstallDir "$INSTDIR"' $0
  StrCmp $0 "0" InstallFiles
  StrCmp $0 "3" 0 InstallProcessesBlocked
  MessageBox MB_ICONSTOP "$(EmptyFolder)"
  Abort
  InstallProcessesBlocked:
  MessageBox MB_ICONSTOP "$(InstallProcesses)"
  Abort
  InstallFiles:
  SetOutPath "$INSTDIR"
  File /r "${STAGE}\*.*"
  File "${ROOT}\packaging\install-preflight.ps1"
  File "${ROOT}\LICENSE"
  File "${ROOT}\NOTICE"
  File "${ROOT}\README.md"
  File "${ROOT}\README.zh-CN.md"

  CreateDirectory "$SMPROGRAMS\AgentRunner"
  CreateShortCut "$SMPROGRAMS\AgentRunner\AgentRunner.lnk" "$INSTDIR\AgentRunner.exe"
  CreateShortCut "$SMPROGRAMS\AgentRunner\Uninstall AgentRunner.lnk" "$INSTDIR\Uninstall.exe"
  ${If} $DesktopShortcut == ${BST_CHECKED}
    CreateShortCut "$DESKTOP\AgentRunner.lnk" "$INSTDIR\AgentRunner.exe"
  ${Else}
    ReadRegDWORD $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "DesktopShortcut"
    ${If} $0 == 1
      Delete "$DESKTOP\AgentRunner.lnk"
    ${EndIf}
  ${EndIf}

  IfFileExists "$PROFILE\.codex\skills\agent-runner\SKILL.md" 0 SubmitSkill
  IfFileExists "$PROFILE\.codex\skills\agent-runner\.agentrunner-owned" SubmitSkill 0
  DetailPrint "Existing agent-runner skill is not owned by this installer; leaving it unchanged."
  Goto CallbackSkill
  SubmitSkill:
    SetOutPath "$PROFILE\.codex\skills\agent-runner"
    File /r "${ROOT}\.agents\skills\agent-runner\*.*"
    FileOpen $0 "$PROFILE\.codex\skills\agent-runner\.agentrunner-owned" w
    FileWrite $0 "AgentRunner 0.2 development preview"
    FileClose $0
    WriteINIStr "$PROFILE\.codex\skills\agent-runner\scripts\runner-location.ini" "Runner" "Executable" "$INSTDIR\runner.exe"
    WriteINIStr "$PROFILE\.codex\skills\agent-runner\scripts\runner-location.ini" "Runner" "DataRoot" "$RunnerDataRoot"

  CallbackSkill:
  IfFileExists "$PROFILE\.codex\skills\agent-runner-callback\SKILL.md" 0 CopyCallbackSkill
  IfFileExists "$PROFILE\.codex\skills\agent-runner-callback\.agentrunner-owned" CopyCallbackSkill 0
  DetailPrint "Existing agent-runner-callback skill is not owned by this installer; leaving it unchanged."
  Goto Registry
  CopyCallbackSkill:
    SetOutPath "$PROFILE\.codex\skills\agent-runner-callback"
    File /r "${ROOT}\.agents\skills\agent-runner-callback\*.*"
    FileOpen $0 "$PROFILE\.codex\skills\agent-runner-callback\.agentrunner-owned" w
    FileWrite $0 "AgentRunner 0.2 development preview"
    FileClose $0
    WriteINIStr "$PROFILE\.codex\skills\agent-runner-callback\scripts\runner-location.ini" "Runner" "Executable" "$INSTDIR\runner.exe"
    WriteINIStr "$PROFILE\.codex\skills\agent-runner-callback\scripts\runner-location.ini" "Runner" "DataRoot" "$RunnerDataRoot"

  Registry:
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "DisplayName" "AgentRunner"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "Publisher" "Tao Mei"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "InstallerLanguage" "$LANGUAGE"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "DesktopShortcut" $DesktopShortcut
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "DisplayIcon" "$INSTDIR\AgentRunner.exe,0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  IfFileExists "$INSTDIR\runner.exe" 0 CheckUninstallProcesses
    ExecWait '"$INSTDIR\runner.exe" service-stop' $0
    StrCmp $0 "0" CheckUninstallProcesses
    MessageBox MB_ICONSTOP "$(UninstallBlocked)"
    Abort
  CheckUninstallProcesses:
  IfFileExists "$INSTDIR\install-preflight.ps1" 0 RemoveFiles
    ExecWait 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\install-preflight.ps1" -InstallDir "$INSTDIR"' $0
    StrCmp $0 "0" RemoveFiles
    MessageBox MB_ICONSTOP "$(UninstallProcesses)"
    Abort
  RemoveFiles:
  ReadRegDWORD $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner" "DesktopShortcut"
  ${If} $0 == 1
    Delete "$DESKTOP\AgentRunner.lnk"
  ${EndIf}
  Delete "$SMPROGRAMS\AgentRunner\AgentRunner.lnk"
  Delete "$SMPROGRAMS\AgentRunner\Uninstall AgentRunner.lnk"
  RMDir "$SMPROGRAMS\AgentRunner"
  IfFileExists "$PROFILE\.codex\skills\agent-runner\.agentrunner-owned" 0 +2
    Call un.RemoveSubmissionSkill
  IfFileExists "$PROFILE\.codex\skills\agent-runner-callback\.agentrunner-owned" 0 +2
    Call un.RemoveCallbackSkill
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\runner.exe"
  Delete "$INSTDIR\AgentRunner.exe"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$INSTDIR\install-preflight.ps1"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\NOTICE"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\README.zh-CN.md"
  RMDir "$INSTDIR"
  DetailPrint "$(DataPreserved)"
SectionEnd

Function un.RemoveSubmissionSkill
  Delete "$PROFILE\.codex\skills\agent-runner\scripts\runner-location.ini"
  Delete "$PROFILE\.codex\skills\agent-runner\scripts\find_runner.ps1"
  RMDir "$PROFILE\.codex\skills\agent-runner\scripts"
  Delete "$PROFILE\.codex\skills\agent-runner\SKILL.md"
  Delete "$PROFILE\.codex\skills\agent-runner\.agentrunner-owned"
  RMDir "$PROFILE\.codex\skills\agent-runner"
FunctionEnd

Function un.RemoveCallbackSkill
  Delete "$PROFILE\.codex\skills\agent-runner-callback\scripts\runner-location.ini"
  Delete "$PROFILE\.codex\skills\agent-runner-callback\scripts\find_runner.ps1"
  Delete "$PROFILE\.codex\skills\agent-runner-callback\SKILL.md"
  Delete "$PROFILE\.codex\skills\agent-runner-callback\scripts\claim_event.ps1"
  Delete "$PROFILE\.codex\skills\agent-runner-callback\scripts\inflight_probe.ps1"
  RMDir "$PROFILE\.codex\skills\agent-runner-callback\scripts"
  Delete "$PROFILE\.codex\skills\agent-runner-callback\.agentrunner-owned"
  RMDir "$PROFILE\.codex\skills\agent-runner-callback"
FunctionEnd
