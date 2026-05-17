# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    ('b1.png', '.'), ('b2.png', '.'), ('b3.png', '.'),
    ('b4.png', '.'), ('b5.png', '.'),
    ('s1.png', '.'), ('s2.png', '.'), ('s3.png', '.'),
    ('s4.png', '.'), ('s5.png', '.'),
    ('s1.mp3', '.'),
]
binaries = []
hiddenimports = []
tmp_ret = collect_all('cv2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('numpy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pygame')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pyautogui')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

excludes = [
    'matplotlib', 'scipy', 'pandas', 'IPython', 'jupyter',
    'notebook', 'setuptools', 'pkg_resources', 'distutils',
    'unittest', 'doctest', 'pdb', 'profile', 'pstats',
    'lib2to3', 'xmlrpc', 'ftplib', 'imaplib', 'poplib',
    'smtplib', 'telnetlib', 'turtle', 'ensurepip', 'curses',
]

a = Analysis(
    ['main.pyw'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SRT매크로',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='i7.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SRT매크로',
)
