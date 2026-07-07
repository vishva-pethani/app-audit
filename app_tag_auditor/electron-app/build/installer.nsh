; installer.nsh — Custom NSIS script hooks for App Tag Auditor Windows installer
; This runs after the main Electron install finishes.

!macro customInstall
  ; Run the PowerShell post-install setup script
  DetailPrint "Running post-install setup (Python, Appium, ADB)..."
  nsExec::ExecToLog 'powershell.exe -ExecutionPolicy Bypass -NoProfile -File "$INSTDIR\resources\app\build\after-install.ps1" -InstallDir "$INSTDIR\resources\app"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION "Post-install setup encountered issues. Check the log at %TEMP%\AppTagAuditor-install.log"
  ${EndIf}
!macroend

!macro customUnInstall
  ; Remove created directories
  RMDir /r "$INSTDIR\resources\app\venv"
  RMDir /r "$INSTDIR\resources\app\.appium"
  RMDir /r "$INSTDIR\resources\app\tmp"
  RMDir /r "$INSTDIR\resources\app\logs"
  RMDir /r "$INSTDIR\resources\app\.sessions"
!macroend
