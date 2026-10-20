"""First-run setup (permissions) and the Support / donate dialog."""

from __future__ import annotations

import sys

from PySide6.QtCore import QProcess, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from .. import APP_NAME, __version__, links
from ..i18n import language, tr
from .icons import icon

MAC = sys.platform == "darwin"

# (key, title, why, System Settings pane)
MAC_PERMISSIONS = [
    ("accessibility", "Accessibility", "Needed to replay clicks and key presses.", "Privacy_Accessibility"),
    ("input", "Input Monitoring", "Needed to record the mouse and keyboard and for the global shortcuts.",
     "Privacy_ListenEvent"),
    ("screen", "Screen Recording", "Only for image search, text recognition (OCR) and AI screen steps.",
     "Privacy_ScreenCapture"),
]


def mac_permission_status() -> dict[str, bool]:
    st = {}
    try:
        from ApplicationServices import AXIsProcessTrusted
        st["accessibility"] = bool(AXIsProcessTrusted())
    except Exception:
        st["accessibility"] = True
    try:
        import Quartz
        st["input"] = bool(Quartz.CGPreflightListenEventAccess())
        st["screen"] = bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        st.setdefault("input", True)
        st.setdefault("screen", True)
    return st


def mac_request(key: str) -> None:
    """Ask macOS to list the app in the pane (and show its prompt), then open the pane."""
    try:
        if key == "accessibility":
            from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        elif key == "input":
            import Quartz
            Quartz.CGRequestListenEventAccess()
        elif key == "screen":
            import Quartz
            Quartz.CGRequestScreenCaptureAccess()
    except Exception:
        pass
    pane = dict((k, p) for k, _, _, p in MAC_PERMISSIONS)[key]
    QDesktopServices.openUrl(QUrl(f"x-apple.systempreferences:com.apple.preference.security?{pane}"))


def restart_app() -> None:
    """Start a fresh copy of the app and quit this one (macOS reads new permissions only at launch)."""
    exe = sys.executable
    if getattr(sys, "frozen", False):
        if MAC and ".app/Contents/MacOS/" in exe:
            QProcess.startDetached("open", ["-n", exe.split(".app/")[0] + ".app"])
        else:
            QProcess.startDetached(exe, sys.argv[1:])
    else:
        QProcess.startDetached(exe, ["-m", "macrorecorder"] + sys.argv[1:])
    QApplication.instance().quit()


def install_guide_url() -> str:
    return links.INSTALL_GUIDE_VI_URL if language() == "vi" else links.INSTALL_GUIDE_URL


class SetupDialog(QDialog):
    """Shown on first launch, when macOS permissions are missing, and from Help → Permissions."""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(tr("Welcome to Actions Recorder"))
        self.setMinimumWidth(600)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icon("app").pixmap(48, 48))
        title = QLabel(f"<b style='font-size:17px'>{tr('Welcome to Actions Recorder')}</b><br>"
                       f"<span>{tr('A free tool to record, edit and replay mouse & keyboard actions.')}</span>")
        title.setWordWrap(True)
        head.addWidget(logo)
        head.addWidget(title, 1)
        lay.addLayout(head)

        self.rows: dict[str, tuple[QLabel, QPushButton]] = {}
        if MAC:
            intro = QLabel(tr("macOS needs your permission before an app may watch or control the mouse and "
                              "keyboard. Click “Allow…”, switch Actions Recorder on in the list that opens, "
                              "then come back here."))
            intro.setWordWrap(True)
            lay.addWidget(intro)
            box = QFrame()
            box.setObjectName("permBox")
            box.setStyleSheet("#permBox{border:1px solid rgba(127,127,127,90);border-radius:8px;}")
            g = QGridLayout(box)
            g.setColumnStretch(1, 1)
            for r, (key, name, why, _) in enumerate(MAC_PERMISSIONS):
                status = QLabel()
                text = QLabel(f"<b>{tr(name)}</b><br><span style='color:gray'>{tr(why)}</span>")
                text.setWordWrap(True)
                btn = QPushButton(tr("Allow…"))
                btn.clicked.connect(lambda _=False, k=key: mac_request(k))
                g.addWidget(status, r, 0, Qt.AlignTop)
                g.addWidget(text, r, 1)
                g.addWidget(btn, r, 2, Qt.AlignVCenter)
                self.rows[key] = (status, btn)
            lay.addWidget(box)
            self.restart_note = QLabel(tr("Already switched on but still marked ❌? macOS applies some permissions "
                                          "only after the app restarts."))
            self.restart_note.setWordWrap(True)
            self.restart_note.setStyleSheet("color:gray")
            lay.addWidget(self.restart_note)
        else:
            info = QLabel(tr("No special permissions are needed on Windows.") + "<br><br>" +
                          tr("To automate programs that run as administrator, start Actions Recorder as "
                             "administrator too (right-click → Run as administrator)."))
            info.setWordWrap(True)
            lay.addWidget(info)

        quick = QLabel("<b>" + tr("Quick start") + "</b><br>" +
                       tr("Press F9 to start or stop recording and F10 to run the macro. Shortcuts can be "
                          "changed in Preferences.") +
                       (" " + tr("On a MacBook, hold fn while pressing F9 / F10.") if MAC else ""))
        quick.setWordWrap(True)
        lay.addWidget(quick)
        help_lbl = QLabel(f"<a href='{install_guide_url()}'>{tr('Installation & permissions guide')}</a>")
        help_lbl.setOpenExternalLinks(True)
        lay.addWidget(help_lbl)

        bottom = QHBoxLayout()
        self.dont_show = QCheckBox(tr("Don't show this again"))
        self.dont_show.setChecked(True)
        bottom.addWidget(self.dont_show)
        bottom.addStretch(1)
        if MAC:
            restart = QPushButton(tr("Restart app"))
            restart.clicked.connect(self._restart)
            bottom.addWidget(restart)
        ok = QPushButton(tr("Done"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        bottom.addWidget(ok)
        lay.addLayout(bottom)

        if MAC:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(1000)
            self.refresh()

    def refresh(self) -> None:
        st = mac_permission_status()
        for key, (status, btn) in self.rows.items():
            ok = st.get(key, True)
            status.setText("✅" if ok else "❌")
            status.setStyleSheet("font-size:18px")
            btn.setEnabled(not ok)
            btn.setText(tr("Allowed") if ok else tr("Allow…"))

    def _restart(self) -> None:
        self._save()
        restart_app()

    def _save(self) -> None:
        self.store.set("ui/onboarded", bool(self.dont_show.isChecked()))

    def done(self, r: int) -> None:
        self._save()
        super().done(r)


def missing_required_mac_permissions() -> bool:
    if not MAC:
        return False
    st = mac_permission_status()
    return not (st.get("accessibility", True) and st.get("input", True))


class SupportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Support Actions Recorder"))
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        heart = QLabel("❤")
        heart.setAlignment(Qt.AlignCenter)
        heart.setStyleSheet("font-size:40px;color:#e5484d")
        lay.addWidget(heart)
        text = QLabel(tr("Actions Recorder is free and open source (MIT license). If it saves you time, "
                         "a small donation helps keep it maintained. Thank you!"))
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignCenter)
        lay.addWidget(text)
        options = links.donate_options()

        def opener(u):
            return lambda _=False: QDesktopServices.openUrl(QUrl(u))

        quick = [o for o in options if o[0] == "amount"]
        if quick:
            row_q = QHBoxLayout()
            for i, (_, label, url) in enumerate(quick):
                b = QPushButton(("☕ " if i == 0 else "🍕 ") + label)
                b.setObjectName("pillRun")
                b.setMinimumHeight(40)
                b.setToolTip(tr("Opens PayPal with this amount filled in"))
                b.clicked.connect(opener(url))
                row_q.addWidget(b)
            lay.addLayout(row_q)
        for kind, label, url in options:
            if kind == "amount":
                continue
            text = tr("PayPal — choose an amount") if kind == "paypal" else \
                tr("GitHub Sponsors — monthly or one-time")
            b = QPushButton(text)
            b.setMinimumHeight(34)
            b.clicked.connect(opener(url))
            lay.addWidget(b)
        if not options:
            lay.addWidget(QLabel(tr("Donation links are not configured yet.")))
        row = QHBoxLayout()
        for label, url in ((tr("⭐ Star on GitHub"), links.REPO_URL), (tr("Report a problem"), links.ISSUES_URL)):
            b = QPushButton(label)
            b.setFlat(True)
            b.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            row.addWidget(b)
        lay.addLayout(row)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignRight)


def about_html() -> str:
    return (f"<h3>{APP_NAME} {__version__}</h3><p>"
            + tr("Record, edit and replay mouse and keyboard macros on Windows and macOS.")
            + "</p><p>" + tr("Free and open source software, MIT license.") + "</p>"
            f"<p><a href='{links.REPO_URL}'>{links.REPO_URL}</a></p>"
            "<p style='color:gray'>Python · Qt (PySide6) · pynput · OpenCV</p>")


__all__ = ["SetupDialog", "SupportDialog", "about_html", "missing_required_mac_permissions", "restart_app"]
