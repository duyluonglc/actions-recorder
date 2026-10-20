# Installing Actions Recorder

[Tiếng Việt](INSTALL.vi.md)

Download the file for your computer from the **[latest release](https://github.com/OWNER/actions-recorder/releases/latest)**:

| Computer | File |
|---|---|
| Windows 10 / 11 (64-bit) | `ActionsRecorder-<version>-Windows-x64.zip` |
| Mac with Apple chip (M1, M2, M3, M4 …) | `ActionsRecorder-<version>-macOS-AppleSilicon.dmg` |
| Mac with Intel processor | `ActionsRecorder-<version>-macOS-Intel.dmg` |

Not sure which Mac you have? Apple menu  → **About This Mac** → look at *Chip* (Apple) or *Processor* (Intel).

> **Why the warnings?** Actions Recorder is free. Removing the first-launch warnings would require paid
> code-signing certificates from Apple and Microsoft, so the app is distributed unsigned
> (macOS: ad-hoc signature). The warnings below appear **once**; follow the steps to open the app.
> Always download from the official Releases page above.

---

## Windows

1. **Unzip** the downloaded file: right-click it → **Extract All…** → *Extract*. Do not run the app from inside the zip.
2. Open the extracted folder and double-click **Actions Recorder.exe**.
3. If **"Windows protected your PC"** (SmartScreen) appears: click **More info** → **Run anyway**.

   This is needed only the first time.
4. That's it — Windows needs no extra permissions.
   - To automate programs that run **as administrator**, start Actions Recorder as administrator too
     (right-click → *Run as administrator*); Windows does not let normal programs control elevated windows.

**Antivirus warning or the .exe disappears?** Tools that record the keyboard and move the mouse look
like spyware to some antivirus heuristics. Actions Recorder keeps everything on your computer (see
[Privacy](#privacy)). You can:
- restore the file from quarantine and add the folder as an exclusion (Windows Security → Virus & threat
  protection → Manage settings → Exclusions), or
- check the download on [VirusTotal](https://www.virustotal.com/), or build the app yourself from source.

**Updating:** delete the old folder and extract the new zip. Your settings and macros are kept.

---

## macOS

### 1. Install

Open the `.dmg` and drag **Actions Recorder** onto **Applications**.

### 2. Open it the first time

macOS blocks apps that are not notarized by Apple:

**macOS 15 Sequoia and newer**
1. Double-click Actions Recorder. A message says Apple could not verify it → click **Done**
   (do **not** choose *Move to Bin*).
2. Open **System Settings → Privacy & Security**, scroll down to *Security*.
3. Next to *"Actions Recorder" was blocked…* click **Open Anyway**, confirm with your password or Touch ID,
   then click **Open Anyway** again.

**macOS 14 Sonoma and older:** right-click (or Control-click) the app → **Open** → **Open**.

**"Actions Recorder is damaged and can't be opened"** — this is the quarantine flag on downloaded files,
not real damage. Open **Terminal** and run:

```bash
xattr -dr com.apple.quarantine "/Applications/Actions Recorder.app"
```

### 3. Grant permissions

On first launch a **Welcome** window lists the permissions with a live ✅ / ❌ status. For each one click
**Allow…** — System Settings opens at the right page — and switch **Actions Recorder** on:

| Permission | Where | Needed for |
|---|---|---|
| **Accessibility** | Privacy & Security → Accessibility | replaying clicks and key presses |
| **Input Monitoring** | Privacy & Security → Input Monitoring | recording, global shortcuts (F9 / F10) |
| **Screen Recording** | Privacy & Security → Screen & System Audio Recording | image search, OCR, AI screen steps (optional) |

Then click **Restart app** — macOS applies Input Monitoring and Screen Recording only after a restart.
You can open the window again at any time from **Help → Permissions…**.

If Actions Recorder is not in a list, click **+**, choose *Applications → Actions Recorder*, and switch it on.

### 4. Function keys on a MacBook

The F-keys control brightness/volume by default. Press **fn + F9** / **fn + F10**, or enable
*System Settings → Keyboard → Keyboard Shortcuts… → Function Keys → "Use F1, F2, etc. keys as standard
function keys"*. You can also choose other shortcuts in **Preferences → Shortcuts**.

### Updating on macOS

Replace the app in *Applications* with the new one. Because the app is not signed with an Apple
Developer ID, macOS may treat the new version as a different app and keep showing ❌ although the switch
looks on. Fix: in each permission list select **Actions Recorder**, click **−** to remove it, then use
**Allow…** in the Welcome window again (Help → Permissions…).

---

## Checking an installation

Run the built-in self-test and attach the output when you [report a problem](https://github.com/OWNER/actions-recorder/issues):

- Windows (Command Prompt, inside the app folder):
  `"Actions Recorder.exe" --self-test report.txt` → then open `report.txt`
- macOS (Terminal):
  `"/Applications/Actions Recorder.app/Contents/MacOS/Actions Recorder" --self-test`

## Privacy

Recorded macros, settings and screenshots stay on your computer. Nothing is sent anywhere, except the
prompt/screenshot of an **AI step** — only if you add one and configure an AI provider yourself (or use a
local model such as Ollama, which keeps everything offline).

## Running from source

```bash
git clone https://github.com/OWNER/actions-recorder.git
cd actions-recorder
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip ...
.venv/bin/python run.py
```

When running from source on macOS, grant the permissions to the **Terminal** (or IDE) you start it from.
