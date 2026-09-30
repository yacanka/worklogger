# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller configuration for the Windows desktop distribution.

`ssl` and `_ssl` are explicit hidden imports because the HTTPS stack reaches
them indirectly through requests/urllib3.  Keeping them in the analysis also
causes PyInstaller to collect the OpenSSL DLLs required by `_ssl.pyd`.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


project_root = Path(SPECPATH)
icon = project_root / "icon.png"
if not icon.is_file():
    raise FileNotFoundError(
        f"Application icon was not found: {icon}. Add icon.png before building."
    )

datas = collect_data_files("certifi")
certificate = project_root / "JIRA_Chain.crt"
if certificate.is_file():
    datas.append((str(certificate), "."))

# Newer jira/requests installations can load cryptography's OpenSSL backend at
# runtime. Its DLLs are not always visible to static import analysis.
binaries = collect_dynamic_libs("cryptography")

analysis = Analysis(
    [str(project_root / "workLogger.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["ssl", "_ssl", "certifi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="workLogger",
    debug=False,
    bootloader_ignore_signals=False,
    # Stripping Windows extension modules/DLLs can make `_ssl.pyd` unloadable.
    # Keep this identical to the known-good SSL build; the icon is metadata only.
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon),
)
