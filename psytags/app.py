"""Application entry point."""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from . import config
from .i18n import set_language
from .ui.theme import apply_theme


def _server_name() -> str:
    import getpass
    return f"psytags-{getpass.getuser()}"


def _send_to_running(paths: list[str]) -> bool:
    """Hand paths to an already running PsyTags. True if one answered."""
    from PySide6.QtNetwork import QLocalSocket
    for _ in range(3):
        sock = QLocalSocket()
        sock.connectToServer(_server_name())
        if sock.waitForConnected(300):
            payload = ("\n".join(paths) if paths else "\x00raise") + "\n\x04"   # \x04 = end
            sock.write(payload.encode("utf-8"))
            sock.waitForBytesWritten(1000)
            ok = sock.waitForReadyRead(2000) and bytes(sock.readAll()).startswith(b"ok")
            sock.disconnectFromServer()
            if ok:
                return True
        import time
        time.sleep(0.1)
    return False


def _start_server(window):
    """Single instance: later launches (context menu, file manager) send their paths
    here. Explorer starts one process per selected file, so paths arriving within a
    short window are collected and loaded together."""
    from PySide6.QtCore import QTimer
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer(window)
    if not server.listen(_server_name()):
        QLocalServer.removeServer(_server_name())       # stale socket from a crash
        if not server.listen(_server_name()):
            return None
    pending: list[str] = []
    flush = QTimer(window)
    flush.setSingleShot(True)
    flush.setInterval(400)

    def do_flush():
        paths = list(dict.fromkeys(pending))
        pending.clear()
        if paths:
            window.load_paths(paths, False)
        window.setWindowState(window.windowState() & ~window.windowState().WindowMinimized)
        window.show()
        window.raise_()
        window.activateWindow()
    flush.timeout.connect(do_flush)

    def on_connection():
        while server.hasPendingConnections():
            sock = server.nextPendingConnection()
            buf = bytearray()

            def read(s=sock, b=buf):
                b.extend(bytes(s.readAll()))
                if not b.endswith(b"\x04"):
                    return                       # message not complete yet
                text = b[:-1].decode("utf-8", "replace")
                b.clear()
                if text.strip() != "\x00raise":
                    pending.extend(p for p in text.split("\n") if p and p != "\x00raise")
                flush.start()
                s.write(b"ok")
                s.flush()
                s.disconnectFromServer()
            sock.readyRead.connect(read)
            sock.disconnected.connect(sock.deleteLater)
            if sock.bytesAvailable():            # data may have arrived before connect()
                read()
    server.newConnection.connect(on_connection)
    return server


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if sys.platform == "win32":
        # Own taskbar group and icon instead of python.exe's.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PsyTags.PsyTags")
        except (AttributeError, OSError):
            pass
    app = QApplication(argv)
    app.setApplicationName(config.APP)
    app.setOrganizationName(config.APP)
    app.setDesktopFileName("psytags")
    opts = config.Options.load()
    set_language(opts.language)
    apply_theme(app)
    # Mp3tag uses the 9pt Windows UI font (12 px at 96 dpi).
    f = QFont(app.font())
    f.setPixelSize(12)
    app.setFont(f)

    from .ui.mainwindow import MainWindow
    paths = [os.path.abspath(a) for a in argv[1:] if not a.startswith("-")]
    if "--new-instance" not in argv and _send_to_running(paths):
        return 0
    w = MainWindow(paths)
    w.show()
    w._ipc_server = _start_server(w)
    # Close (and save) properly on SIGTERM/SIGINT, e.g. at logout. Python only runs
    # signal handlers between bytecodes, so wake the interpreter periodically.
    import signal
    from PySide6.QtCore import QTimer
    for name in ("SIGTERM", "SIGINT", "SIGHUP"):      # SIGHUP does not exist on Windows
        sig = getattr(signal, name, None)
        if sig is not None:
            signal.signal(sig, lambda *_: QTimer.singleShot(0, w.close))
    wake = QTimer()
    wake.start(500)
    wake.timeout.connect(lambda: None)
    return app.exec()
