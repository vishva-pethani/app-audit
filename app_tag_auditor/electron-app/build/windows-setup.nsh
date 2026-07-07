; windows-setup.nsh
; NSIS custom script fragment — runs after electron-builder completes installation.
; Calls our PowerShell post-install script to set up Python venv, Appium, Android SDK, etc.

!macro customInstall
  DetailPrint "Running App Tag Auditor post-install setup..."
  nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\resources\app\build\after-install.ps1" -InstallDir "$INSTDIR\resources\app"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION "Post-install setup encountered an issue (exit code $0). The app may still work if prerequisites are already installed. Check logs at $INSTDIR\resources\app\logs\install.log"
  ${EndIf}
!macroend

!macro customUnInstall
  DetailPrint "Cleaning up App Tag Auditor..."
  nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -Recurse -Force \"$INSTDIR\resources\app\venv\" -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force \"$INSTDIR\resources\app\.appium\" -ErrorAction SilentlyContinue"'
!macroend
