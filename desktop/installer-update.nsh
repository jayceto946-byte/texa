; Runs only for --updated on an existing installation. First installs and manual
; reinstalls retain electron-builder's installer, uninstaller and signing flow.
!include FileFunc.nsh
!include "${__FILEDIR__}/installer-user-migration.nsh"

!macro customHeader
  !ifndef BUILD_UNINSTALLER
    Var texaCandidate
    Var texaBackup
    Var texaParent
    Var texaInstallPath
    Var texaManifest
    Var texaFile
    Var texaPath
    Var texaSize
    Var texaActualSize
    Var texaCount
    Var texaIndex
    Var texaOldVersion
    Var texaOldDisplayName
    Var texaOldSize
    Var texaArchive
    Var texaPhase
    !insertmacro texaMigrationHeader

    Function TexaRecordPhase
      ${If} $installMode == "all"
        SetShellVarContext current
      ${EndIf}
      ${GetParent} "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}" $0
      CreateDirectory $0
      WriteINIStr "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}.transaction.ini" update version "${VERSION}"
      WriteINIStr "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}.transaction.ini" update phase "$texaPhase"
      ${If} $installMode == "all"
        SetShellVarContext all
      ${EndIf}
      ClearErrors
    FunctionEnd

    ; Wait for the prepared Electron exit, without NSIS trying to terminate
    ; the running application. A timeout leaves the existing installation intact.
    Function TexaWaitForExit
      StrCpy $texaIndex 0
      texa_wait_loop:
        ${nsProcess::FindProcess} "${APP_EXECUTABLE_FILENAME}" $R0
        StrCmp $R0 603 texa_wait_done
        StrCmp $R0 0 0 texa_wait_failed
        IntOp $texaIndex $texaIndex + 1
        IntCmp $texaIndex 40 texa_wait_failed
        Sleep 200
        Goto texa_wait_loop
      texa_wait_failed:
        SetErrors
        Return
      texa_wait_done:
        ClearErrors
    FunctionEnd

    Function TexaValidateCandidate
      ClearErrors
      FileOpen $texaManifest "$texaCandidate\resources\texa-update-files.txt" r
      IfErrors texa_manifest_failed
      FileReadUTF16LE $texaManifest $texaPath
      StrCmp $texaPath "TEXA-UPDATE-FILES-1$\r$\n" 0 texa_manifest_close_failed
      FileReadUTF16LE $texaManifest $texaCount
      StrCpy $texaCount $texaCount -2
      IntCmp $texaCount 0 texa_manifest_close_failed texa_manifest_close_failed
      StrCpy $texaIndex 0
      texa_manifest_loop:
        IntCmp $texaIndex $texaCount texa_manifest_end
        ClearErrors
        FileReadUTF16LE $texaManifest $texaPath
        IfErrors texa_manifest_close_failed
        StrCpy $texaPath $texaPath -2
        FileReadUTF16LE $texaManifest $texaSize
        IfErrors texa_manifest_close_failed
        StrCpy $texaSize $texaSize -2
        FileOpen $texaFile "$texaCandidate\$texaPath" r
        IfErrors texa_manifest_close_failed
        FileSeek $texaFile 0 END $texaActualSize
        FileClose $texaFile
        StrCmp $texaSize $texaActualSize 0 texa_manifest_close_failed
        IntOp $texaIndex $texaIndex + 1
        Goto texa_manifest_loop
      texa_manifest_end:
        FileReadUTF16LE $texaManifest $texaPath
        StrCmp $texaPath "END$\r$\n" 0 texa_manifest_close_failed
        FileClose $texaManifest
        ClearErrors
        Return
      texa_manifest_close_failed:
        FileClose $texaManifest
      texa_manifest_failed:
        SetErrors
    FunctionEnd
  !endif
!macroend

!macro texaExtractArchive ARCH FILES_ARCH
  ; Match electron-builder's normal extraction: this is already a 7z/zip.
  ; Otherwise NSIS embeds a recompressed second copy of the entire payload.
  !ifdef COMPRESS
    SetCompress off
  !endif
  File "/oname=$PLUGINSDIR\texa-app.${COMPRESSION_METHOD}" "${APP_${ARCH}}"
  !ifdef COMPRESS
    SetCompress "${COMPRESS}"
  !endif
  StrCpy $texaArchive "$PLUGINSDIR\texa-app.${COMPRESSION_METHOD}"
  SetOutPath $texaCandidate
  !ifdef ZIP_COMPRESSION
    nsisunz::Unzip "$texaArchive" "$texaCandidate"
    Pop $0
    StrCmp $0 "success" 0 texa_prepare_failed
  !else
    Nsis7z::Extract "$texaArchive"
  !endif
  !ifmacrodef customFiles_${FILES_ARCH}
    ; Upstream pre-compressed asset macros write to $INSTDIR explicitly.
    ; Redirect them to the candidate, never into the still-installed version.
    StrCpy $INSTDIR $texaCandidate
    !insertmacro customFiles_${FILES_ARCH}
    StrCpy $INSTDIR $texaInstallPath
  !endif
!macroend

!macro customInit
  StrCpy $texaMigrating 0
  StrCpy $texaCleanupPending 0
  StrCpy $texaLinksTouched 0
  ReadRegStr $texaMachinePath HKCU "${INSTALL_REGISTRY_KEY}" MigrationMachinePath
  ${If} $texaMachinePath != ""
    ${If} ${FileExists} "$texaMachinePath\${APP_EXECUTABLE_FILENAME}"
      StrCpy $texaCleanupPending 1
    ${Else}
      DeleteRegValue HKCU "${INSTALL_REGISTRY_KEY}" MigrationMachinePath
    ${EndIf}
  ${EndIf}
  ${If} ${isUpdated}
  ${AndIf} ${FileExists} "$INSTDIR\${APP_EXECUTABLE_FILENAME}"
    ; Prepare under the original user's token. Only the old machine uninstaller
    ; will request elevation, after the complete user installation is published.
    ${If} $installMode == "all"
      StrCpy $texaPhase "migration_preparing"
      Call TexaPrepareUserMigration
      IfErrors texa_migration_unavailable
    ${EndIf}

    StrCpy $texaPhase "preparing"
    Call TexaRecordPhase
    Call TexaWaitForExit
    IfErrors texa_prepare_failed
    InitPluginsDir
    StrCpy $texaInstallPath $INSTDIR
    ReadRegStr $texaOldVersion SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" DisplayVersion
    ReadRegStr $texaOldDisplayName SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" DisplayName
    ReadRegDWORD $texaOldSize SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" EstimatedSize
    ${GetParent} "$INSTDIR" $texaParent
    ClearErrors
    GetTempFileName $texaCandidate "$texaParent"
    IfErrors texa_prepare_failed
    Delete $texaCandidate
    CreateDirectory $texaCandidate
    IfErrors texa_prepare_failed
    GetTempFileName $texaBackup "$texaParent"
    IfErrors texa_prepare_failed
    Delete $texaBackup

    !ifdef APP_BUILD_DIR
      SetOutPath $texaCandidate
      File /r "${APP_BUILD_DIR}\*.*"
    !else
      !ifdef APP_ARM64
        ${If} ${IsNativeARM64}
          !insertmacro texaExtractArchive ARM64 arm64
        ${Else}
      !endif
      !ifdef APP_64
        !ifdef APP_32
          ${If} ${RunningX64}
            !insertmacro texaExtractArchive 64 x64
          ${Else}
            !insertmacro texaExtractArchive 32 ia32
          ${EndIf}
        !else
          !insertmacro texaExtractArchive 64 x64
        !endif
      !else
        !ifdef APP_32
          !insertmacro texaExtractArchive 32 ia32
        !endif
      !endif
      !ifdef APP_ARM64
        ${EndIf}
      !endif
    !endif
    Call TexaValidateCandidate
    IfErrors texa_prepare_failed
    ; The generated uninstaller is part of this candidate too. Do not execute
    ; the old uninstaller: it deletes the shortcut target before extraction.
    ClearErrors
    SetOutPath $texaCandidate
    File "/oname=${UNINSTALL_FILENAME}" "${UNINSTALLER_OUT_FILE}"
    !ifdef UNINSTALLER_ICON
      File /oname=uninstallerIcon.ico "${UNINSTALLER_ICON}"
    !endif
    IfErrors texa_prepare_failed
    SetOutPath $PLUGINSDIR
    ; If the user reopened the shortcut while extraction was in progress,
    ; leave that running client intact instead of replacing its resources.
    ${nsProcess::FindProcess} "${APP_EXECUTABLE_FILENAME}" $R0
    StrCmp $R0 603 0 texa_prepare_failed
    StrCpy $texaPhase "candidate_ready"
    Call TexaRecordPhase
    ClearErrors
    ${If} $texaMigrating != 1
      Rename "$INSTDIR" "$texaBackup"
      IfErrors texa_prepare_failed
    ${EndIf}
    Rename "$texaCandidate" "$INSTDIR"
    IfErrors texa_restore_old

    ; User updates retain their paths/links. Migration publishes a complete
    ; HKCU registration and user shortcuts before removing the machine install.
    ClearErrors
    ${If} $texaMigrating == 1
      Call TexaWriteUserInstall
    ${Else}
      WriteRegStr SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" DisplayVersion "${VERSION}"
      WriteRegStr SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" DisplayName "${UNINSTALL_DISPLAY_NAME}"
      WriteRegDWORD SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" EstimatedSize ${ESTIMATED_SIZE}
    ${EndIf}
    IfErrors texa_restore_old
    ${If} $texaMigrating == 1
      Call TexaCleanupMachineInstall
    ${EndIf}
    System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
    StrCpy $texaLaunchArgs "--updated"
    ${If} $texaCleanupPending == 1
      StrCpy $texaLaunchArgs "$texaLaunchArgs --texa-migration-cleanup-pending"
    ${EndIf}
    ${If} ${isForceRun}
      ClearErrors
      ${If} ${UAC_IsAdmin}
        ; Never launch the application with the elevated installer's token.
        ${StdUtils.ExecShellAsUser} $0 "$INSTDIR\${APP_EXECUTABLE_FILENAME}" "open" "$texaLaunchArgs"
        ${If} $0 != "ok"
        ${AndIf} $0 != "fallback"
          Goto texa_launch_failed
        ${EndIf}
      ${Else}
        ; Launch the prepared local executable directly; do not route internal
        ; restarts through Explorer/shortcut ShellExecute and its file-open UI.
        Exec '"$INSTDIR\${APP_EXECUTABLE_FILENAME}" $texaLaunchArgs'
        IfErrors texa_launch_failed
      ${EndIf}
    ${EndIf}

    ; Match the normal installer cache used for future differential downloads.
    ${If} $installMode == "all"
      SetShellVarContext current
    ${EndIf}
    ${GetParent} "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}" $0
    CreateDirectory $0
    CopyFiles /SILENT "$EXEPATH" "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}"
    ${If} $installMode == "all"
      SetShellVarContext all
    ${EndIf}
    ${If} $texaMigrating != 1
      RMDir /r $texaBackup
    ${EndIf}
    StrCpy $texaPhase "committed"
    ${If} $texaCleanupPending == 1
      StrCpy $texaPhase "migration_cleanup_pending"
    ${EndIf}
    Call TexaRecordPhase
    SetErrorLevel 0
    Quit

    texa_launch_failed:
      ${If} $texaMigrating != 1
        Goto texa_restore_old
      ${EndIf}
      ; The old installation may already be removed. Keep the complete user
      ; installation and its working shortcuts if automatic relaunch failed.
      StrCpy $texaPhase "migration_launch_failed"
      Call TexaRecordPhase
      MessageBox MB_OK|MB_ICONEXCLAMATION "Texa 已安装到当前用户目录，请使用桌面或开始菜单快捷方式打开。" /SD IDOK
      SetErrorLevel 1603
      Quit

    texa_restore_old:
      ; A published candidate must first move out of the original path. Never
      ; recursively delete either version to make room for a rollback.
      ${If} ${FileExists} "$INSTDIR\${APP_EXECUTABLE_FILENAME}"
        Rename "$INSTDIR" "$texaCandidate"
        IfErrors texa_restore_failed
      ${EndIf}
      ${If} $texaMigrating == 1
        Call TexaRollbackUserInstall
      ${Else}
        Rename "$texaBackup" "$INSTDIR"
        IfErrors texa_restore_failed
        WriteRegStr SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" DisplayVersion "$texaOldVersion"
        WriteRegStr SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" DisplayName "$texaOldDisplayName"
        WriteRegDWORD SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" EstimatedSize $texaOldSize
      ${EndIf}
      System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
      StrCpy $texaPhase "rolled_back"
      Goto texa_prepare_failed

    texa_restore_failed:
      ${If} $texaMigrating == 1
        StrCpy $texaBackup $texaMachinePath
      ${EndIf}
      StrCpy $texaPhase "recovery_required"
      Call TexaRecordPhase
      MessageBox MB_OK|MB_ICONSTOP "Texa 更新未完成。旧程序保留在：$texaBackup。请保留该目录以便恢复。" /SD IDOK
      SetErrorLevel 1603
      Quit

    texa_prepare_failed:
      ${If} $texaPhase != "rolled_back"
        StrCpy $texaPhase "prepare_failed"
      ${EndIf}
      Call TexaRecordPhase
      SetOutPath $PLUGINSDIR
      ${If} $texaCandidate != ""
        RMDir /r $texaCandidate
      ${EndIf}
      ${If} $texaMigrating == 1
        StrCpy $INSTDIR $texaMachinePath
      ${EndIf}
      ${If} ${isForceRun}
      ${AndIf} ${FileExists} "$INSTDIR\${APP_EXECUTABLE_FILENAME}"
        ${StdUtils.ExecShellAsUser} $0 "$INSTDIR\${APP_EXECUTABLE_FILENAME}" "open" "--texa-update-failed"
      ${EndIf}
      MessageBox MB_OK|MB_ICONSTOP "Texa 更新未能完成，旧程序已保留或恢复。请重新打开 Texa 后重试。" /SD IDOK
      SetErrorLevel 1603
      Quit

    texa_migration_unavailable:
      Call TexaRecordPhase
      ${If} ${isForceRun}
        ${StdUtils.ExecShellAsUser} $0 "$texaMachinePath\${APP_EXECUTABLE_FILENAME}" "open" "--texa-update-failed"
      ${EndIf}
      MessageBox MB_OK|MB_ICONSTOP "Texa 无法迁移：当前用户已有安装或目标目录已存在，或旧版卸载程序缺失。旧安装已保留，请先检查用户目录中的 Texa。" /SD IDOK
      SetErrorLevel 1603
      Quit
  ${EndIf}
!macroend
