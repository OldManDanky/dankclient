#!/usr/bin/env python3
"""Wrap the built folder in an installer.

The Windows build already produces exactly what an installer has to lay down
-- an interpreter, the client, and two launchers -- so this is mostly the
bookkeeping: a component for every file, a stable identity for every component,
and the handful of declarations that make Windows treat a second install as an
upgrade of the first rather than a second copy.

    python3 tools/build_msi.py          build dist/dankclient, then the MSI

It uses wixl, from msitools, which builds MSIs on Linux -- so this can be
produced from the same machine as everything else rather than needing a
Windows build host.

    sudo apt install wixl
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from mud import NAME, SLUG, __version__  # noqa: E402

#: Never change this.  Windows recognises a new version as an upgrade of an
#: old one by matching upgrade codes, so a changed one installs a second copy
#: beside the first and neither knows about the other.
UPGRADE_CODE = "6F2A9C41-7B3D-4E58-9A16-2C7E5D840B93"

#: Per-user, into LocalAppData.  Program Files would need an administrator,
#: and asking a player to elevate to install a MUD client is asking a lot for
#: something that only ever writes inside their own profile anyway.
PROGRAMS = "Programs"

#: A component's identity has to be stable across builds for an upgrade to
#: replace a file rather than leave two.  Derived from the path, so it is the
#: same every time without anything having to be written down.
NAMESPACE = uuid.UUID("1b671a64-40d5-491e-99b0-da01ff1f3341")


def guid(text: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{SLUG}/{text}")).upper()


def ident(text: str) -> str:
    """A WiX identifier: letters, digits and underscores, and not too long."""
    clean = "".join(c if c.isalnum() else "_" for c in text)
    if not clean or clean[0].isdigit():
        clean = "f_" + clean
    # Identifiers are capped at 72 characters, and python's own tree has some
    # long ones; a hash of the whole path keeps them distinct after trimming.
    if len(clean) > 60:
        clean = clean[:52] + "_" + guid(text)[:8]
    return clean


def tree(root: Path):
    """Every directory and file under `root`, depth first, as XML."""
    lines: list[str] = []
    components: list[str] = []

    def walk(where: Path, depth: int) -> None:
        pad = "  " * depth
        for path in sorted(where.iterdir()):
            rel = path.relative_to(root).as_posix()
            if path.is_dir():
                lines.append(
                    f'{pad}<Directory Id="d_{ident(rel)}" '
                    f'Name="{escape(path.name)}">')
                walk(path, depth + 1)
                lines.append(f"{pad}</Directory>")
            else:
                cid = f"c_{ident(rel)}"
                components.append(cid)
                lines.append(
                    f'{pad}<Component Id="{cid}" Guid="{guid(rel)}">\n'
                    f'{pad}  <File Id="f_{ident(rel)}" '
                    f'Name="{escape(path.name)}" '
                    f'Source="{escape(str(path))}" KeyPath="yes"/>\n'
                    f"{pad}</Component>")

    walk(root, 5)
    return "\n".join(lines), components


def licence_rtf(plain: Path) -> str:
    """The GPL as RTF, because the licence dialog will not read anything else.

    Not a conversion so much as an escaping: the text is the text, wrapped in
    the smallest header a reader will accept.
    """
    body = plain.read_text(encoding="utf-8", errors="replace")
    body = (body.replace("\\", r"\\\\").replace("{", r"\{").replace("}", r"\}")
                .replace("\n", r"\par" + "\n"))
    return (r"{\rtf1\ansi\deff0{\fonttbl{\f0\fmodern Courier New;}}"
            r"\fs16 " + body + "}")


def close_script() -> str:
    """PowerShell that closes a running client before any file is replaced.

    The way a person would: close its window, and the client saves and
    disconnects on its own -- the log and the map go to disk, the bots stop,
    no `quit` is sent, exactly as Disconnect does.  Only if a window was
    closed is there anything to wait for, and then no longer than it takes.
    Whatever is still running after that is stopped: a process whose program
    is in this client's folder, or an Edge (or Chrome) running the client's
    own window profile.  Nothing else on the machine is touched.

    It finds them by *part* of a path, never by $env:LOCALAPPDATA.  0.2.10's
    and 0.2.11's did, and upgrading to 0.2.11 over a running client closed
    nothing.  The likeliest reason is that the installer's service starts
    this with its own environment, whose LOCALAPPDATA is not the player's.
    Where it writes down what it did is asked of Windows for this user
    rather than read from the environment, so if it fails again there is
    something to read: %LOCALAPPDATA%\\dankclient\\installer.log.
    Only this session's processes: running as the service, it would otherwise
    see every user's.
    """
    return f"""$ErrorActionPreference = 'SilentlyContinue'
$program = '\\{PROGRAMS}\\{NAME}\\'
$window = '\\{SLUG}\\window'
$session = (Get-Process -Id $PID).SessionId
$log = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) '{SLUG}\\installer.log'
function Say($text) {{ Add-Content -Path $log -Value ((Get-Date -Format s) + '  ' + $text) }}
function Get-Mine {{
  Get-CimInstance Win32_Process | Where-Object {{ $_.SessionId -eq $session }}
}}
function Get-Client {{
  Get-Mine | Where-Object {{
    $_.ExecutablePath -and $_.ExecutablePath.IndexOf($program, [StringComparison]::OrdinalIgnoreCase) -ge 0 }}
}}
function Get-ClientWindow {{
  Get-Mine | Where-Object {{
    $_.CommandLine -and $_.CommandLine.IndexOf($window, [StringComparison]::OrdinalIgnoreCase) -ge 0 }}
}}
Say ('installer: closing a running client (session ' + $session + ', as ' + [Environment]::UserName + ')')
$closed = $false
foreach ($w in @(Get-ClientWindow)) {{
  $p = Get-Process -Id $w.ProcessId
  if ($p -and $p.MainWindowHandle -ne [IntPtr]::Zero) {{
    if ($p.CloseMainWindow()) {{ $closed = $true; Say ('closed its window, process ' + $p.Id) }}
  }}
}}
if ($closed) {{
  $until = (Get-Date).AddSeconds(15)
  while (@(Get-Client).Count -gt 0 -and (Get-Date) -lt $until) {{ Start-Sleep -Milliseconds 250 }}
}}
$left = @(Get-Client) + @(Get-ClientWindow)
foreach ($c in $left) {{ Stop-Process -Id $c.ProcessId -Force; Say ('stopped ' + $c.Name + ' ' + $c.ProcessId) }}
if (-not $closed -and $left.Count -eq 0) {{ Say 'no client was running' }}
exit 0
"""


def close_encoded() -> str:
    """The script as -EncodedCommand wants it: UTF-16LE, then base64.

    Encoded, it carries no quotes, brackets or braces for the installer to
    read as its own [PROPERTY] syntax.
    """
    import base64
    return base64.b64encode(close_script().encode("utf-16-le")).decode("ascii")


def source(root: Path) -> str:
    body, components = tree(root)
    refs = "\n".join(f'      <ComponentRef Id="{c}"/>' for c in components)
    launcher = str(root / f"{SLUG}.cmd")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="{escape(NAME)}" Language="1033"
           Version="{__version__}" Manufacturer="OldManDanky"
           UpgradeCode="{UPGRADE_CODE}">
    <Package InstallerVersion="200" Compressed="yes"
             InstallScope="perUser"
             Description="{escape(NAME)} {__version__}"
             Comments="A MIP-native MUD client for 3Kingdoms. GPLv3."/>

    <!-- Replace an older one rather than sit beside it. -->
    <Upgrade Id="{UPGRADE_CODE}">
      <UpgradeVersion Minimum="0.0.0" Maximum="{__version__}"
                      IncludeMinimum="yes" IncludeMaximum="no"
                      Property="OLDERFOUND"/>
    </Upgrade>
    <!-- After everything is installed, not before it.

         Component ids here are a hash of the file path, so a new version
         shares them with the old one. File costing runs at sequence 1000, five
         hundred before the old product would have been removed at 1501, and it
         saw python\\pythonw.exe already on disk under the same component, byte
         for byte the same file, and decided there was no work to do. The
         removal then deleted it and InstallFiles never put it back: 0.2.0
         upgraded over 0.1.0 into an install with no interpreter in it.

         Late instead. The new files go down first, taking each shared
         component's reference count to two, and removing the old product only
         takes it back to one, so the files stay. It also means a failed
         install leaves the working older one in place, which is the better way
         round to fail. (No double hyphens in here: XML comments forbid them,
         and wixl says only "Extra content at the end of the document".) -->
    <InstallExecuteSequence>
      <Custom Action="FindPowerShell" After="CostFinalize"/>
      <Custom Action="CloseClient" After="FindPowerShell">NOT UPGRADINGPRODUCTCODE</Custom>
      <RemoveExistingProducts After="InstallFinalize"/>
    </InstallExecuteSequence>

    <!-- A running client first.  Its interpreter holds files this is about to
         replace, and Windows would otherwise stop to ask about files in use,
         or worse, want a restart.  So close it, before InstallValidate checks:
         its window first, which makes the client save and disconnect itself,
         then anything of its still running.  See close_script.

         Two actions because wixl has no Directory attribute on a custom
         action: one puts PowerShell's path in a property, the other runs
         whatever that property names (type 50), with the script itself in a
         property of its own, since a custom action's command is a 255
         character column and the encoded script is thousands.  Return is
         ignore: a machine where this cannot run gets the files in use
         question it always got, and an install that goes on.  Not when this
         version is itself being removed by a newer one: that one has already
         closed the client, and it only put a second window on the screen. -->
    <Property Id="DANKCLOSE" Value="{close_encoded()}"/>
    <CustomAction Id="FindPowerShell" Property="DANKPS"
                  Value="[SystemFolder]WindowsPowerShell\\v1.0\\powershell.exe"/>
    <CustomAction Id="CloseClient" Property="DANKPS" Execute="immediate"
                  Return="ignore"
                  ExeCommand="-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand [DANKCLOSE]"/>

    <Media Id="1" Cabinet="{SLUG}.cab" EmbedCab="yes"/>

    <!-- Without one, Windows shows a generic executable box in the Start
         Menu, on the taskbar and in Apps & Features, and a program that looks
         like every other unlabelled program is one people lose. -->
    <Icon Id="app.ico" SourceFile="{escape(str(root / "mud" / "ui" / "icon.ico"))}"/>
    <Property Id="ARPPRODUCTICON" Value="app.ico"/>

    <!-- Silence is not a confirmation.  The first installed run put itself
         somewhere without saying where, which leaves you with a Start Menu
         entry and no idea what it did. -->
    <UIRef Id="WixUI_Minimal"/>
    <!-- Set by an action, not as a Property.  The dialog shows
         [WIXUI_EXITDIALOGOPTIONALTEXT], and Windows Installer fills in a
         reference once: references inside the value it found are not filled
         in again, so a Property here put the words [INSTALLDIR] on screen.
         An action that sets a property does format its value, and after
         CostFinalize the folders have their real paths. -->
    <CustomAction Id="SayWhere" Property="WIXUI_EXITDIALOGOPTIONALTEXT"
                  Value="Installed to [INSTALLDIR]. Your map, characters, triggers and session logs live separately in [LocalAppDataFolder]{SLUG}, so updating this program never touches them. That folder also holds client.log, which is where it writes down anything that goes wrong."/>
    <InstallUISequence>
      <Custom Action="SayWhere" After="CostFinalize"/>
    </InstallUISequence>

    <!-- What Apps &amp; Features shows.  Without these it is a name and
         nothing else. -->
    <Property Id="ARPURLINFOABOUT"
              Value="https://github.com/OldManDanky/dankclient"/>
    <Property Id="ARPHELPLINK"
              Value="https://github.com/OldManDanky/dankclient/issues"/>
    <Property Id="ARPNOREPAIR" Value="1"/>

    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="LocalAppDataFolder">
        <Directory Id="ProgramsDir" Name="{PROGRAMS}">
          <Directory Id="INSTALLDIR" Name="{escape(NAME)}">
{body}
          </Directory>
        </Directory>
      </Directory>

      <Directory Id="ProgramMenuFolder">
        <Directory Id="MenuDir" Name="{escape(NAME)}">
          <Component Id="c_shortcut" Guid="{guid('shortcut')}">
            <Shortcut Id="s_play" Name="{escape(NAME)}"
                      Description="Play 3Kingdoms"
                      Target="[INSTALLDIR]{SLUG}.cmd"
                      WorkingDirectory="INSTALLDIR"
                      Icon="app.ico"/>
            <RemoveFolder Id="MenuDir" On="uninstall"/>
            <RegistryValue Root="HKCU"
                           Key="Software\\OldManDanky\\{SLUG}"
                           Name="installed" Type="integer" Value="1"
                           KeyPath="yes"/>
          </Component>
        </Directory>
      </Directory>
    </Directory>

    <Feature Id="Complete" Title="{escape(NAME)}" Level="1">
{refs}
      <ComponentRef Id="c_shortcut"/>
    </Feature>
  </Product>
</Wix>
"""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="folder",
                    default=str(HERE / "dist" / SLUG),
                    help="the built client folder")
    ap.add_argument("--out", default=str(
        HERE / "dist" / f"{SLUG}-{__version__}.msi"))
    ap.add_argument("--wxs-only", action="store_true",
                    help="write the WiX source and stop")
    args = ap.parse_args(argv[1:])

    root = Path(args.folder)
    if not root.exists():
        print(f"no {root} -- run tools/build_windows.py first", file=sys.stderr)
        return 1

    wxs = Path(args.out).with_suffix(".wxs")
    wxs.parent.mkdir(parents=True, exist_ok=True)
    (wxs.parent / "License.rtf").write_text(licence_rtf(HERE / "LICENSE"))
    wxs.write_text(source(root))
    files = sum(1 for p in root.rglob("*") if p.is_file())
    print(f"  {files} files -> {wxs}")
    if args.wxs_only:
        return 0

    if shutil.which("wixl") is None:
        print("  wixl is not installed:  sudo apt install wixl", file=sys.stderr)
        return 2

    # The dialogs live in an extension that is off unless it is asked for.
    done = subprocess.run(["wixl", "--ext", "ui", "-o", args.out, str(wxs)],
                          capture_output=True, text=True)
    if done.returncode != 0:
        sys.stderr.write(done.stdout + done.stderr)
        return done.returncode
    size = Path(args.out).stat().st_size
    print(f"  {args.out} ({size // 1048576} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
