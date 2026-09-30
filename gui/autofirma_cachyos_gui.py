#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GUI de AutoFirma para CachyOS/Arch Linux.

Usa PyQt6 + PTY real y delega la compilación/instalación al instalador
del repositorio. La GUI no ejecuta como root.
"""
from __future__ import annotations

import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QPlainTextEdit,
    QInputDialog, QProgressBar, QVBoxLayout, QWidget
)

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "instalar_autofirma.sh"
if not INSTALLER.is_file():
    INSTALLER = Path(__file__).resolve().parent / "instalar_autofirma.sh"

NSS_DIR = Path.home() / ".pki" / "nssdb"
AUTOFIRMA_DIR = Path.home() / ".afirma" / "Autofirma"

ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
PROMPT_RE = re.compile(r"(?:password|contraseña|clave).*[:?]\s*$", re.I)


def run_capture(args, input_text=None):
    return subprocess.run(args, input=input_text, text=True, capture_output=True)


def have(cmd):
    return shutil.which(cmd) is not None


def root_cert():
    for name in (
        "AutoFirma_ROOT.cer",
        "AutoFirma_ROOT.pem",
        "Autofirma_ROOT.cer",
        "Autofirma_ROOT.pem",
        "autofirma_root.cer",
        "autofirma_root.pem",
    ):
        path = AUTOFIRMA_DIR / name
        if path.is_file():
            return path
    return None


def sha256_cert(path):
    p = run_capture(["openssl", "x509", "-in", str(path), "-noout", "-fingerprint", "-sha256"])
    if p.returncode:
        return None
    return p.stdout.strip().replace("sha256 Fingerprint=", "").replace("SHA256 Fingerprint=", "")


def nss_certificates(db):
    p = run_capture(["certutil", "-L", "-d", f"sql:{db}"])
    return p.returncode, p.stdout, p.stderr


def nss_fingerprint(db, nickname):
    p = run_capture(["certutil", "-L", "-d", f"sql:{db}", "-n", nickname, "-a"])
    if p.returncode:
        return None
    q = subprocess.run(
        ["openssl", "x509", "-noout", "-fingerprint", "-sha256"],
        input=p.stdout, text=True, capture_output=True
    )
    if q.returncode:
        return None
    return q.stdout.strip().replace("sha256 Fingerprint=", "").replace("SHA256 Fingerprint=", "")


def pkcs12_info(path, password):
    base = ["openssl", "pkcs12", "-in", str(path), "-clcerts", "-nokeys", "-passin", "stdin"]
    attempts = [base]
    if have("openssl"):
        attempts.append(["openssl", "pkcs12", "-legacy", "-in", str(path),
                         "-clcerts", "-nokeys", "-passin", "stdin"])
    for command in attempts:
        p = subprocess.run(command, input=password, text=True, capture_output=True)
        if p.returncode:
            continue
        q = subprocess.run(
            ["openssl", "x509", "-noout", "-fingerprint", "-sha256", "-dates"],
            input=p.stdout, text=True, capture_output=True
        )
        if q.returncode:
            continue
        values = {}
        for line in q.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        fp = values.get("sha256 Fingerprint") or values.get("SHA256 Fingerprint")
        return fp, values.get("notBefore"), values.get("notAfter")
    return None, None, None


def firefox_profiles():
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    bases = [
        Path(xdg) / "mozilla" / "firefox",
        Path.home() / ".mozilla" / "firefox",
        Path.home() / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox",
    ]
    result = []
    for base in bases:
        ini = base / "profiles.ini"
        if not ini.is_file():
            continue
        for line in ini.read_text(errors="replace").splitlines():
            if not line.startswith("Path="):
                continue
            value = line.split("=", 1)[1].strip()
            p = Path(value)
            if not p.is_absolute():
                p = base / p
            if (p / "cert9.db").exists():
                result.append(p)
        for p in base.glob("*.default*"):
            if (p / "cert9.db").exists():
                result.append(p)
    return list(dict.fromkeys(result))


def trust_root_in_db(db, cert_path):
    fp = sha256_cert(cert_path)
    if not fp:
        return False, "No se pudo leer el certificado raíz."
    nickname = "AutoFirma ROOT"
    existing = nss_fingerprint(db, nickname)
    if existing and existing == fp:
        return True, f"{db}: AutoFirma ROOT ya está instalado."
    if existing:
        p = run_capture([
            "certutil", "-M", "-d", f"sql:{db}", "-n", nickname, "-t", "C,,"
        ])
        if p.returncode:
            return False, f"{db}: no se pudo actualizar la confianza: {p.stderr.strip()}"
        return True, f"{db}: confianza actualizada."
    p = run_capture([
        "certutil", "-A", "-d", f"sql:{db}", "-n", nickname,
        "-t", "C,,", "-i", str(cert_path)
    ])
    if p.returncode:
        return False, f"{db}: no se pudo importar AutoFirma ROOT: {p.stderr.strip()}"
    return True, f"{db}: AutoFirma ROOT importado con confianza C,,."


class PtyRunner:
    def __init__(self, command, on_output, on_done, on_prompt):
        self.command = command
        self.on_output = on_output
        self.on_done = on_done
        self.on_prompt = on_prompt
        self.pid = None
        self.fd = None
        self.prompt_buffer = ""
        self.finished = False
        self._last_cancel = 0.0

    def start(self):
        import pty
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            try:
                os.execvp(self.command[0], self.command)
            except OSError as exc:
                os.write(2, f"ERROR ejecutando {self.command[0]}: {exc}\n".encode())
                os._exit(127)
        os.set_blocking(self.fd, False)

    def _close_fd(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def _reap(self):
        if self.pid is None:
            return False
        try:
            done, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            self.pid = None
            return False
        if not done:
            return False
        code = os.waitstatus_to_exitcode(status)
        pid = self.pid
        self.pid = None
        self._finish(code)
        return True

    def _finish(self, code):
        if self.finished:
            return
        self.finished = True
        self._close_fd()
        self.on_done(code)

    def poll(self):
        if self.finished:
            return
        if self.fd is not None:
            try:
                ready, _, _ = select.select([self.fd], [], [], 0)
                if ready:
                    try:
                        data = os.read(self.fd, 8192)
                    except OSError:
                        data = b""
                    if data:
                        text = data.decode("utf-8", "replace")
                        clean = ANSI_RE.sub("", text)
                        self.prompt_buffer = (self.prompt_buffer + clean)[-1000:]
                        last_line = self.prompt_buffer.splitlines()[-1] if self.prompt_buffer.splitlines() else ""
                        if PROMPT_RE.search(last_line.strip()):
                            self.on_prompt(True)
                        self.on_output(text)
                    else:
                        self._close_fd()
            except (OSError, ValueError):
                self._close_fd()
        if not self._reap() and self.fd is None and self.pid is not None:
            return

    def send(self, text):
        if self.fd is not None and not self.finished:
            try:
                os.write(self.fd, text.encode())
                self.on_prompt(False)
            except OSError:
                pass

    def cancel(self):
        if self.finished:
            return
        now = time.monotonic()
        if now - self._last_cancel < 0.8:
            if self.pid is not None:
                try:
                    os.killpg(self.pid, signal.SIGKILL)
                except OSError:
                    try:
                        os.kill(self.pid, signal.SIGKILL)
                    except OSError:
                        pass
        else:
            if self.fd is not None:
                try:
                    os.write(self.fd, b"\x03")
                except OSError:
                    pass
            self.on_prompt(False)
        self._last_cancel = now


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("csr79a", "AutoFirmaCachyOS")
        self.runner = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_runner)
        self.setWindowTitle("AutoFirma · CachyOS")
        QApplication.setApplicationName("AutoFirma CachyOS")
        self.resize(1050, 720)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        title = QLabel("AutoFirma · CachyOS")
        title.setFont(QFont("Sans", 22, QFont.Weight.Bold))
        root.addWidget(title)
        root.addWidget(QLabel("Instalación, almacén NSS, certificado personal e integración con navegadores"))

        grid = QGridLayout()
        root.addLayout(grid)
        cards = [
            ("AutoFirma", "Instala o reconstruye el cliente", "Instalar / reconstruir", self.install),
            ("NSS", "Crea o revisa ~/.pki/nssdb", "Comprobar NSS", self.nss_check),
            ("Certificado", "Añade tu .p12 / .pfx al almacén", "Importar certificado", self.import_cert),
            ("Navegadores", "Firefox y navegadores basados en Chromium", "Confiar cert. en navegadores", self.trust_browsers),
            ("Estado", "Revisa instalación e integración", "Comprobar estado", self.status),
            ("Versiones", "Consulta las versiones oficiales", "Versiones oficiales", self.versions),
            ("Actualizar", "Preparado para futura actualización", "Actualizar AutoFirma", self.update_note),
        ]
        for i, (head, desc, button, fn) in enumerate(cards):
            box = QGroupBox(head)
            lay = QVBoxLayout(box)
            label = QLabel(desc)
            label.setWordWrap(True)
            lay.addWidget(label)
            btn = QPushButton(button)
            btn.clicked.connect(fn)
            lay.addWidget(btn)
            grid.addWidget(box, i // 2, i % 2)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Monospace", 10))
        root.addWidget(self.log, 1)

        log_row = QHBoxLayout()
        save_log = QPushButton("Guardar log")
        save_log.clicked.connect(self.save_log)
        clear_log = QPushButton("Limpiar log")
        clear_log.clicked.connect(self.log.clear)
        log_row.addWidget(save_log)
        log_row.addWidget(clear_log)
        log_row.addStretch()
        root.addLayout(log_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        root.addWidget(self.progress)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Entrada para el proceso (sudo / s / n / etc.)")
        self.input.returnPressed.connect(self.send_input)
        row.addWidget(self.input, 1)
        send = QPushButton("Enviar")
        send.clicked.connect(self.send_input)
        row.addWidget(send)
        self.cancel = QPushButton("Cancelar")
        self.cancel.clicked.connect(self.cancel_runner)
        self.cancel.setEnabled(False)
        row.addWidget(self.cancel)
        root.addLayout(row)

    def set_password_mode(self, enabled):
        self.input.setEchoMode(
            QLineEdit.EchoMode.Password if enabled else QLineEdit.EchoMode.Normal
        )
        self.input.setPlaceholderText(
            "Contraseña (oculta)" if enabled else "Entrada para el proceso (sudo / s / n / etc.)"
        )

    def write(self, text):
        clean = ANSI_RE.sub("", text).replace("\r", "\n")
        if clean:
            self.log.appendPlainText(clean.rstrip("\n"))
            self.log.ensureCursorVisible()

    def run_pty(self, title, command):
        if self.runner:
            QMessageBox.warning(self, "Proceso activo", "Termina o cancela el proceso actual antes de iniciar otro.")
            return
        self.set_password_mode(False)
        self.write(f"\n=== {title} ===")
        self.write("$ " + " ".join(command))
        self.runner = PtyRunner(command, self.write, self.finished, self.set_password_mode)
        try:
            self.runner.start()
        except Exception as exc:
            self.runner = None
            self.write(f"ERROR iniciando proceso: {exc}")
            return
        self.progress.show()
        self.cancel.setEnabled(True)
        self.timer.start(40)

    def _poll_runner(self):
        if self.runner:
            self.runner.poll()

    def finished(self, code):
        self.timer.stop()
        self.progress.hide()
        self.cancel.setEnabled(False)
        self.set_password_mode(False)
        self.write(f"=== Proceso terminado: código {code} ===")
        self.runner = None

    def send_input(self):
        if self.runner:
            self.runner.send(self.input.text() + "\n")
            self.input.clear()

    def cancel_runner(self):
        if self.runner:
            self.runner.cancel()
            self.write("Cancelación solicitada. Una segunda pulsación fuerza la finalización.")

    def install(self):
        if not INSTALLER.is_file():
            QMessageBox.critical(self, "Error", f"No se encuentra {INSTALLER}")
            return
        QMessageBox.information(
            self, "Permisos",
            "El instalador puede solicitar la contraseña de sudo.\n"
            "Cuando aparezca la petición, el campo inferior se ocultará automáticamente."
        )
        self.run_pty("Instalar / reconstruir AutoFirma", ["bash", str(INSTALLER)])

    def nss_check(self):
        if not have("certutil"):
            QMessageBox.critical(self, "Falta NSS", "Instala el paquete nss: sudo pacman -S nss")
            return
        if not NSS_DIR.exists():
            NSS_DIR.mkdir(parents=True, exist_ok=True)
            p = run_capture(["certutil", "-N", "-d", f"sql:{NSS_DIR}", "--empty-password"])
            if p.returncode:
                self.write("ERROR creando NSS: " + (p.stderr or p.stdout).strip())
                return
            os.chmod(NSS_DIR, 0o700)
            self.write(f"NSS creado: {NSS_DIR} (contraseña vacía)")
        else:
            self.write(f"NSS ya existe: {NSS_DIR}")
            self.write("No se recrea, no se borra y no se modifica.")
        if not (NSS_DIR / "cert9.db").exists():
            self.write("ADVERTENCIA: no se encuentra cert9.db en el almacén.")
        rc, out, err = nss_certificates(NSS_DIR)
        if rc == 0:
            self.write(out.strip() or "NSS válido y actualmente vacío.")
        else:
            self.write("ADVERTENCIA: el almacén existe pero certutil no puede abrirlo.")
            self.write(err.strip())

    def import_cert(self):
        if not NSS_DIR.exists():
            self.nss_check()
        if not NSS_DIR.exists():
            return
        last_dir = self.settings.value("certificateDirectory", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar certificado personal", last_dir,
            "Certificados PKCS#12 (*.p12 *.pfx)"
        )
        if not path:
            return
        self.settings.setValue("certificateDirectory", str(Path(path).parent))
        password, ok = self.password_dialog("Contraseña del certificado", "Contraseña del .p12/.pfx:")
        if not ok:
            return
        cert = Path(path)
        self.write(f"Comprobando certificado personal: {cert.name}")
        fingerprint, not_before, not_after = pkcs12_info(cert, password)
        if not fingerprint:
            self.write("ERROR: OpenSSL 3 no pudo leer el PKCS#12. Se probó también el modo -legacy.")
            self.write("Comprueba la contraseña o el formato del fichero.")
            return
        self.write("Huella SHA-256: " + fingerprint)
        if not_before:
            self.write("Válido desde: " + not_before)
        if not_after:
            self.write("Válido hasta: " + not_after)
        if not_after:
            from datetime import datetime, timezone
            try:
                expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                if expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                    self.write("AVISO: el certificado parece estar caducado. La importación no se bloquea.")
            except ValueError:
                pass

        rc, listing, _ = nss_certificates(NSS_DIR)
        if rc != 0:
            self.write("ERROR: el almacén NSS no se puede abrir.")
            return
        for line in listing.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("Certificate") or stripped.startswith("==="):
                continue
            nickname = stripped.split()[0]
            if nss_fingerprint(NSS_DIR, nickname) == fingerprint:
                self.write(f"El certificado ya está presente en NSS como: {nickname}")
                return

        self.write(f"Importando certificado personal: {cert.name}")
        p = subprocess.run(
            ["pk12util", "-d", f"sql:{NSS_DIR}", "-i", str(cert), "-w", "/dev/stdin"],
            input=password + "\n", text=True, capture_output=True
        )
        if p.returncode:
            self.write("ERROR al importar: " + (p.stderr or p.stdout).strip())
            return
        self.write("Certificado importado correctamente.")

    def password_dialog(self, title, label):
        return QInputDialog.getText(self, title, label, QLineEdit.EchoMode.Password)

    def trust_browsers(self):
        if not have("certutil"):
            QMessageBox.critical(self, "Falta NSS", "Instala el paquete nss: sudo pacman -S nss")
            return
        cert = root_cert()
        if not cert:
            QMessageBox.warning(
                self, "AutoFirma ROOT no encontrado",
                f"No se encontró AutoFirma ROOT en {AUTOFIRMA_DIR}.\n\n"
                "Ejecuta AutoFirma una vez para que genere su CA local."
            )
            return
        targets = []
        if NSS_DIR.is_dir() and (NSS_DIR / "cert9.db").exists():
            targets.append(NSS_DIR)
        targets.extend(firefox_profiles())
        targets = list(dict.fromkeys(targets))
        if not targets:
            self.write("No se encontraron almacenes NSS de navegador.")
            return
        for db in targets:
            ok, msg = trust_root_in_db(db, cert)
            self.write(("OK: " if ok else "ERROR: ") + msg)
        self.write("Cierra completamente Firefox/Chromium/Chrome/Brave antes de volver a probar.")
        if (Path.home() / ".var" / "app" / "org.mozilla.firefox").exists():
            self.write("Se revisó también la ruta de perfiles de Firefox Flatpak.")

    def status(self):
        self.write("\n=== Estado de AutoFirma ===")
        for cmd in ["java", "certutil", "pk12util", "openssl", "xdg-mime"]:
            self.write(f"{cmd}: {'OK' if have(cmd) else 'FALTA'}")
        self.write(f"Instalador: {'OK' if INSTALLER.is_file() else 'FALTA'}")
        self.write(f"Jar: {'OK' if Path('/usr/share/java/autofirma/autofirma.jar').is_file() else 'FALTA'}")
        self.write(f"NSS: {'EXISTE' if NSS_DIR.exists() else 'NO EXISTE'}")
        self.write(f"CA local: {'EXISTE' if root_cert() else 'NO EXISTE (arranca AutoFirma primero)'}")
        p = run_capture(["xdg-mime", "query", "default", "x-scheme-handler/afirma"])
        self.write("afirma://: " + (p.stdout.strip() or "no registrado"))

    def update_note(self):
        self.write("\n=== Actualizar AutoFirma ===")
        self.write("La actualización automática todavía no modifica la instalación.")
        self.write("El instalador actual está fijado a clienteafirma v1.9.2.")
        self.write("Primero se consultan las versiones con el botón «Versiones oficiales».")

    def versions(self):
        self.run_pty("Consultar versiones oficiales", [
            "bash", "-lc",
            "echo 'Tags recientes de clienteafirma:'; "
            "git ls-remote --tags --refs --sort=v:refname "
            "https://github.com/ctt-gob-es/clienteafirma.git | tail -10"
        ])

    def save_log(self):
        last_dir = self.settings.value("logDirectory", str(Path.home()))
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar log", str(Path(last_dir) / "autofirma.log"),
            "Texto (*.log *.txt)"
        )
        if not path:
            return
        self.settings.setValue("logDirectory", str(Path(path).parent))
        try:
            Path(path).write_text(self.log.toPlainText() + "\n", encoding="utf-8")
            self.write(f"Log guardado en: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el log:\n{exc}")


def main():
    if sys.version_info < (3, 10):
        print("Se requiere Python 3.10 o superior.", file=sys.stderr)
        raise SystemExit(1)
    app = QApplication(sys.argv)
    w = App()
    w.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
