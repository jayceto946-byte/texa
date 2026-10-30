; Migrate only application files and installation metadata. The original user
; process installs into its own profile; only the old machine uninstaller may
; elevate, so credentials entered in UAC cannot select a different data profile.
!macro texaMigrationHeader
  Var texaMigrating
  Var texaMachinePath
  Var texaCleanupPending
  Var texaDesktopLink
  Var texaMenuLink
  Var texaLinksTouched
  Var texaLaunchArgs

  Function TexaPrepareUserMigration
    StrCpy $texaMachinePath $INSTDIR
    StrCpy $texaMigrating 1
    SetShellVarContext current
    StrCpy $installMode CurrentUser
    ; Do not inherit the old updater's /D=Program Files argument.
    StrCpy $INSTDIR "$LOCALAPPDATA\Programs\${APP_FILENAME}"
    ReadRegStr $0 HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation
    ${If} $0 != ""
      ; There is already a user installation. Do not overwrite its identity.
      SetErrors
      Return
    ${EndIf}
    ${If} ${FileExists} "$INSTDIR\*.*"
    ${OrIfNot} ${FileExists} "$texaMachinePath\${UNINSTALL_FILENAME}"
      SetErrors
      Return
    ${EndIf}
    ClearErrors
    CreateDirectory "$LOCALAPPDATA\Programs"
  FunctionEnd

  Function TexaWriteUserInstall
    ClearErrors
    WriteRegStr HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation "$INSTDIR"
    WriteRegStr HKCU "${INSTALL_REGISTRY_KEY}" KeepShortcuts "true"
    WriteRegStr HKCU "${INSTALL_REGISTRY_KEY}" ShortcutName "${SHORTCUT_NAME}"
    WriteRegStr HKCU "${UNINSTALL_REGISTRY_KEY}" DisplayName "${UNINSTALL_DISPLAY_NAME}"
    WriteRegStr HKCU "${UNINSTALL_REGISTRY_KEY}" DisplayVersion "${VERSION}"
    WriteRegStr HKCU "${UNINSTALL_REGISTRY_KEY}" UninstallString '$\"$INSTDIR\${UNINSTALL_FILENAME}$\" /currentuser'
    WriteRegStr HKCU "${UNINSTALL_REGISTRY_KEY}" QuietUninstallString '$\"$INSTDIR\${UNINSTALL_FILENAME}$\" /currentuser /S'
    WriteRegStr HKCU "${UNINSTALL_REGISTRY_KEY}" DisplayIcon "$INSTDIR\${APP_EXECUTABLE_FILENAME},0"
    WriteRegDWORD HKCU "${UNINSTALL_REGISTRY_KEY}" EstimatedSize ${ESTIMATED_SIZE}
    WriteRegDWORD HKCU "${UNINSTALL_REGISTRY_KEY}" NoModify 1
    WriteRegDWORD HKCU "${UNINSTALL_REGISTRY_KEY}" NoRepair 1
    WriteRegStr HKCU "${INSTALL_REGISTRY_KEY}" MigrationMachinePath "$texaMachinePath"
    IfErrors texa_user_install_failed

    StrCpy $texaDesktopLink "$DESKTOP\${SHORTCUT_NAME}.lnk"
    !ifdef MENU_FILENAME
      StrCpy $texaMenuLink "$SMPROGRAMS\${MENU_FILENAME}\${SHORTCUT_NAME}.lnk"
      WriteRegStr HKCU "${INSTALL_REGISTRY_KEY}" MenuDirectory "${MENU_FILENAME}"
    !else
      StrCpy $texaMenuLink "$SMPROGRAMS\${SHORTCUT_NAME}.lnk"
    !endif
    IfErrors texa_user_install_failed
    ; Preserve any existing user shortcuts if publishing metadata/links fails.
    !ifndef DO_NOT_CREATE_DESKTOP_SHORTCUT
      ${If} ${FileExists} "$texaDesktopLink"
        CopyFiles /SILENT "$texaDesktopLink" "$PLUGINSDIR\texa-original-desktop.lnk"
        IfErrors texa_user_install_failed
      ${EndIf}
    !endif
    !ifndef DO_NOT_CREATE_START_MENU_SHORTCUT
      ${If} ${FileExists} "$texaMenuLink"
        CopyFiles /SILENT "$texaMenuLink" "$PLUGINSDIR\texa-original-menu.lnk"
        IfErrors texa_user_install_failed
      ${EndIf}
    !endif
    StrCpy $texaLinksTouched 1
    !ifndef DO_NOT_CREATE_DESKTOP_SHORTCUT
      CreateShortCut "$texaDesktopLink" "$INSTDIR\${APP_EXECUTABLE_FILENAME}"
      IfErrors texa_user_install_failed
      WinShell::SetLnkAUMI "$texaDesktopLink" "${APP_ID}"
    !endif
    !ifndef DO_NOT_CREATE_START_MENU_SHORTCUT
      !ifdef MENU_FILENAME
        CreateDirectory "$SMPROGRAMS\${MENU_FILENAME}"
      !endif
      CreateShortCut "$texaMenuLink" "$INSTDIR\${APP_EXECUTABLE_FILENAME}"
      IfErrors texa_user_install_failed
      WinShell::SetLnkAUMI "$texaMenuLink" "${APP_ID}"
    !endif
    ClearErrors
    Return
    texa_user_install_failed:
      SetErrors
  FunctionEnd

  Function TexaRollbackUserInstall
    DeleteRegKey HKCU "${INSTALL_REGISTRY_KEY}"
    DeleteRegKey HKCU "${UNINSTALL_REGISTRY_KEY}"
    ${If} $texaLinksTouched == 1
      !ifndef DO_NOT_CREATE_DESKTOP_SHORTCUT
        Delete "$texaDesktopLink"
        ${If} ${FileExists} "$PLUGINSDIR\texa-original-desktop.lnk"
          CopyFiles /SILENT "$PLUGINSDIR\texa-original-desktop.lnk" "$texaDesktopLink"
        ${EndIf}
      !endif
      !ifndef DO_NOT_CREATE_START_MENU_SHORTCUT
        Delete "$texaMenuLink"
        ${If} ${FileExists} "$PLUGINSDIR\texa-original-menu.lnk"
          CopyFiles /SILENT "$PLUGINSDIR\texa-original-menu.lnk" "$texaMenuLink"
        ${EndIf}
      !endif
    ${EndIf}
  FunctionEnd

  Function TexaCleanupMachineInstall
    StrCpy $texaCleanupPending 1
    StrCpy $texaPhase "user_install_ready"
    Call TexaRecordPhase
    ; Same waitable uninstaller protocol as electron-builder, explicitly keeping
    ; application data. /allusers targets HKLM even after HKCU is registered.
    ClearErrors
    CopyFiles /SILENT "$texaMachinePath\${UNINSTALL_FILENAME}" "$PLUGINSDIR\texa-machine-uninstaller.exe"
    IfErrors texa_machine_cleanup_done
    ExecWait '$\"$PLUGINSDIR\texa-machine-uninstaller.exe$\" /S /KEEP_APP_DATA /allusers --updated _?=$texaMachinePath' $0
    IfErrors texa_machine_cleanup_done
    StrCmp $0 0 0 texa_machine_cleanup_done
    ${If} ${FileExists} "$texaMachinePath\${APP_EXECUTABLE_FILENAME}"
      Goto texa_machine_cleanup_done
    ${EndIf}
    ReadRegStr $0 HKLM "${INSTALL_REGISTRY_KEY}" InstallLocation
    ${If} $0 != ""
      Goto texa_machine_cleanup_done
    ${EndIf}
    StrCpy $texaCleanupPending 0
    texa_machine_cleanup_done:
      ${If} $texaCleanupPending == 1
        WriteRegStr HKCU "${INSTALL_REGISTRY_KEY}" MigrationMachinePath "$texaMachinePath"
      ${Else}
        DeleteRegValue HKCU "${INSTALL_REGISTRY_KEY}" MigrationMachinePath
      ${EndIf}
      ClearErrors
  FunctionEnd
!macroend

; New interactive installs select current-user scope. Explicit administrative
; /allusers installs remain supported for managed installs and CI fixtures.
!macro customInstallMode
  ${IfNot} ${isForAllUsers}
    StrCpy $isForceCurrentInstall 1
  ${EndIf}
!macroend
