#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GUI de AutoFirma para CachyOS/Arch Linux.

Arquitectura: PyQt6 + PTY real, siguiendo el formato de las GUI de
debian-trixie-setup y fedora-plasma-setup. No duplica la compilación:
para instalar/reconstruir ejecuta instalar_autofirma.sh.
"""
from __future__ import annotations

import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QPlainTextEdit,
    QProgressBar, QVBoxLayout, QWidget
)

ROOT = Path(__file__).resolve().parents[1]
NSS_DIR = Path.home() / ".pki" / "nssdb"
AUTOFIRMA_DIR = Path.home() / ".afirma" / "Autofirma"
AUTOFIRMA_ROOT = AUTOFIRMA_DIR / "AutoFirma_ROOT.cer"
INSTALLER = ROOT / "instalar_autofirma.sh"

ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
PROMPT_RE = re.compile(r"(?:password|contraseña|clave).*[:?]\s*$", re.I)

def run_capture(args, input_text=None):
    return subprocess.run(args, input=input_text, text=True, capture_output=True)

def have(cmd):
    return subprocess.run(["bash", "-lc", f"command -v {cmd} >/dev/null 2>&1"]).returncode == 0

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
    q = subprocess.run(["openssl", "x509", "-noout", "-fingerprint", "-sha256"],
                       input=p.stdout, text=True, capture_output=True)
    if q.returncode:
        return None
    return q.stdout.strip().replace("sha256 Fingerprint=", "").replace("SHA256 Fingerprint=", "")

def pkcs12_fingerprint(path, password):
    p = subprocess.run(
        ["openssl", "pkcs12", "-in", str(path), "-clcerts", "-nokeys", "-passin", "stdin"],
        input=password, text=True, capture_output=True
    )
    if p.returncode:
        return None
    q = subprocess.run(
        ["openssl", "x509", "-noout", "-fingerprint", "-sha256"],
        input=p.stdout, text=True, capture_output=True
    )
    if q.returncode:
        return None
    return q.stdout.strip().replace("sha256 Fingerprint=", "").replace("SHA256 Fingerprint=", "")

def pkcs12_fingerprint(path, password):
    p = subprocess.run(
        ["openssl", "pkcs12", "-in", str(path), "-clcerts", "-nokeys", "-passin", "stdin"],
        input=password, text=True, capture_output=True
    )
    if p.returncode:
        return None
    q = subprocess.run(
        ["openssl", "x509", "-noout", "-fingerprint", "-sha256"],
        input=p.stdout, text=True, capture_output=True
    )
    if q.returncode:
        return None
    return q.stdout.strip().replace("sha256 Fingerprint=", "").replace("SHA256 Fingerprint=", "")

def firefox_profiles():
    bases = []
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    bases.append(Path(xdg) / "mozilla" / "firefox")
    bases.append(Path.home() / ".mozilla" / "firefox")
    result = []
    for base in bases:
        ini = base / "profiles.ini"
        if not ini.is_file():
            continue
        current = None
        for line in ini.read_text(errors="replace").splitlines():
            if line.startswith("Path="):
                current = line.split("=", 1)[1].strip()
                p = Path(current)
                if not p.is_absolute():
                    p = base / p
                if (p / "cert9.db").exists():
                    result.append(p)
        if not result:
            for p in base.glob("*.default*"):
                if (p / "cert9.db").exists():
                    result.append(p)
    return list(dict.fromkeys(result))

def trust_root_in_db(db, cert_path):
    fp = sha256_cert(cert_path)
    if not fp:
        return False, "No se pudo leer el certificado raíz."
    nick = "AutoFirma ROOT"
    existing = nss_fingerprint(db, nick)
    if existing and existing == fp:
        return True, f"{db}: AutoFirma ROOT ya está instalado."
    if existing:
        p = run_capture(["certutil", "-M", "-d", f"sql:{db}", "-n", nick, "-t", "C,,"])
        if p.returncode:
            return False, f"{db}: no se pudo actualizar la confianza: {p.stderr.strip()}"
        return True, f"{db}: confianza actualizada."
    p = run_capture(["certutil", "-A", "-d", f"sql:{db}", "-n", nick,
                     "-t", "C,,", "-i", str(cert_path)])
    if p.returncode:
        return False, f"{db}: no se pudo importar AutoFirma ROOT: {p.stderr.strip()}"
    return True, f"{db}: AutoFirma ROOT importado con confianza C,,."

class PtyRunner:
    def __init__(self, command, on_output, on_done):
        self.command = command
        self.on_output = on_output
        self.on_done = on_done
        self.pid = None
        self.fd = None
        self.buffer = b""
        self._last_cancel = 0

    def start(self):
        import pty
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execvp(self.command[0], self.command)
        os.set_blocking(self.fd, False)

    def poll(self):
        if self.fd is None:
            return
        try:
            ready, _, _ = select.select([self.fd], [], [], 0)
            if ready:
                data = os.read(self.fd, 8192)
                if data:
                    self.on_output(data.decode("utf-8", "replace"))
                else:
                    self.finish()
        except (OSError, EOFError):
            self.finish()
        if self.pid:
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                self.finish(os.waitstatus_to_exitcode(status))

    def send(self, text):
        if self.fd is not None:
            try:
                os.write(self.fd, text.encode())
            except OSError:
                pass

    def cancel(self):
        if not self.pid:
            return
        now = time.monotonic()
        if now - self._last_cancel < 0.8:
            try:
                os.kill(self.pid, 9)
            except OSError:
                pass
        else:
            try:
                os.kill(self.pid, 2)
            except OSError:
                pass
        self._last_cancel = now

    def finish(self, code=None):
        if self.fd is None:
            return
        fd, pid = self.fd, self.pid
        self.fd = None
        try:
            os.close(fd)
        except OSError:
            pass
        if code is None and pid:
            try:
                _, status = os.waitpid(pid, os.WNOHANG)
                code = os.waitstatus_to_exitcode(status) if status else 130
            except OSError:
                code = 130
        self.on_done(code if code is not None else 0)

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.runner = None
        self.current_action = ""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_runner)
        self.setWindowTitle("AutoFirma · CachyOS")
        self.resize(1050, 720)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        title = QLabel("AutoFirma · CachyOS")
        title.setFont(QFont("Sans", 22, QFont.Weight.Bold))
        root.addWidget(title)
        sub = QLabel("Instalación, almacén NSS, certificado personal e integración con navegadores")
        root.addWidget(sub)

        grid = QGridLayout()
        root.addLayout(grid)

        cards = [
            ("1. AutoFirma", "Instalar / reconstruir AutoFirma", self.install),
            ("2. NSS", "Crear o comprobar ~/.pki/nssdb", self.nss_check),
            ("3. Certificado", "Importar certificado .p12 / .pfx", self.import_cert),
            ("4. Navegadores", "Confiar en AutoFirma ROOT", self.trust_browsers),
            ("5. Estado", "Comprobar instalación e integración", self.status),
            ("6. Versiones", "Consultar versiones oficiales disponibles", self.versions),
            ("7. Actualizar", "Preparado para futura actualización", self.update_note),
        ]
        for i, (head, text, fn) in enumerate(cards):
            box = QGroupBox(head)
            lay = QVBoxLayout(box)
            lab = QLabel(text)
            lab.setWordWrap(True)
            lay.addWidget(lab)
            b = QPushButton("Abrir")
            b.clicked.connect(fn)
            lay.addWidget(b)
            grid.addWidget(box, i // 2, i % 2)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Monospace", 10))
        root.addWidget(self.log, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        root.addWidget(self.progress)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Entrada para el proceso (contraseña / s / n / etc.)")
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

    def write(self, text):
        clean = ANSI_RE.sub("", text).replace("\r", "\n")
        if clean:
            self.log.appendPlainText(clean.rstrip("\n"))
            self.log.ensureCursorVisible()

    def run_pty(self, title, command):
        if self.runner:
            QMessageBox.warning(self, "Proceso activo", "Termina o cancela el proceso actual antes de iniciar otro.")
            return
        self.current_action = title
        self.write(f"\n=== {title} ===")
        self.write("$ " + " ".join(command))
        self.runner = PtyRunner(command, self.write, self.finished)
        self.runner.start()
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
        self.write(f"=== Proceso terminado: código {code} ===")
        self.runner = None

    def send_input(self):
        if self.runner:
            self.runner.send(self.input.text() + "\n")
            self.input.clear()

    def cancel_runner(self):
        if self.runner:
            self.runner.cancel()
            self.write("Se ha solicitado la cancelación. Pulsa Cancelar otra vez si el proceso no termina.")

    def install(self):
        if not INSTALLER.is_file():
            QMessageBox.critical(self, "Error", f"No se encuentra {INSTALLER}")
            return
        self.run_pty("Instalar / reconstruir AutoFirma", ["bash", str(INSTALLER)])

    def nss_check(self):
        if not have("certutil"):
            QMessageBox.critical(self, "Falta NSS", "Instala el paquete nss: sudo pacman -S nss")
            return
        if not NSS_DIR.exists():
            p = run_capture(["certutil", "-N", "-d", f"sql:{NSS_DIR}", "--empty-password"])
            if p.returncode:
                self.write("ERROR creando NSS: " + (p.stderr or p.stdout).strip())
                return
            os.chmod(NSS_DIR, 0o700)
            self.write(f"NSS creado: {NSS_DIR} (contraseña vacía)")
        else:
            self.write(f"NSS ya existe: {NSS_DIR}")
            self.write("No se recrea, no se borra y no se modifica.")
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
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar certificado personal", str(Path.home()),
                                               "Certificados PKCS#12 (*.p12 *.pfx)")
        if not path:
            return
        password, ok = self.password_dialog("Contraseña del certificado", "Contraseña del .p12/.pfx:")
        if not ok:
            return
        cert = Path(path)
        self.write(f"Comprobando certificado personal: {cert.name}")
        fingerprint = pkcs12_fingerprint(cert, password)
        if not fingerprint:
            self.write("ERROR: no se pudo leer el certificado del PKCS#12. Comprueba la contraseña.")
            return
        self.write("Huella SHA-256: " + fingerprint)
        rc, listing, _ = nss_certificates(NSS_DIR)
        if rc != 0:
            self.write("ERROR: el almacén NSS no se puede abrir.")
            return
        for line in listing.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("Certificate") or stripped.startswith("==="):
                continue
            nickname = stripped.split()[0]
            existing = nss_fingerprint(NSS_DIR, nickname)
            if existing == fingerprint:
                self.write(f"El certificado ya está presente en NSS como: {nickname}")
                return

        self.write(f"Importando certificado personal: {cert.name}")
        import tempfile
        pwfile = None
        try:
            fd, name = tempfile.mkstemp(prefix="autofirma-pw-", text=True)
            os.write(fd, password.encode())
            os.close(fd)
            os.chmod(name, 0o600)
            pwfile = name
            p = subprocess.run(
                ["pk12util", "-d", f"sql:{NSS_DIR}", "-i", str(cert), "-w", pwfile],
                text=True, capture_output=True
            )
        finally:
            if pwfile:
                try: os.unlink(pwfile)
                except OSError: pass
        if p.returncode:
            self.write("ERROR al importar: " + (p.stderr or p.stdout).strip())
            return
        self.write("Certificado importado correctamente.")
        rc, out, _ = nss_certificates(NSS_DIR)
        if rc == 0:
            self.write(out.strip())

    def password_dialog(self, title, label):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(label)
        edit = QLineEdit(box)
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        box.layout().addWidget(edit, 1, 1)
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        result = box.exec()
        return edit.text(), result == QMessageBox.StandardButton.Ok

    def trust_browsers(self):
        if not have("certutil"):
            QMessageBox.critical(self, "Falta NSS", "Instala el paquete nss: sudo pacman -S nss")
            return
        if not AUTOFIRMA_ROOT.is_file():
            QMessageBox.warning(self, "AutoFirma ROOT no encontrado",
                                f"No existe todavía:\n{AUTOFIRMA_ROOT}\n\nEjecuta AutoFirma una vez para que genere su CA local.")
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
            ok, msg = trust_root_in_db(db, AUTOFIRMA_ROOT)
            self.write(("OK: " if ok else "ERROR: ") + msg)
        self.write("Cierra completamente Firefox/Chromium/Chrome/Brave antes de volver a probar.")

    def status(self):
        self.write("\n=== Estado de AutoFirma ===")
        for cmd in ["java", "certutil", "pk12util", "openssl", "xdg-mime"]:
            self.write(f"{cmd}: {'OK' if have(cmd) else 'FALTA'}")
        self.write(f"Instalador: {'OK' if INSTALLER.is_file() else 'FALTA'}")
        self.write(f"Jar: {'OK' if Path('/usr/share/java/autofirma/autofirma.jar').is_file() else 'FALTA'}")
        self.write(f"NSS: {'EXISTE' if NSS_DIR.exists() else 'NO EXISTE'}")
        self.write(f"CA local: {'EXISTE' if AUTOFIRMA_ROOT.is_file() else 'NO EXISTE (arranca AutoFirma primero)'}")
        p = run_capture(["xdg-mime", "query", "default", "x-scheme-handler/afirma"])
        self.write("afirma://: " + (p.stdout.strip() or "no registrado"))

    def update_note(self):
        self.write("\n=== Actualizar AutoFirma ===")
        self.write("La actualización automática todavía no modifica la instalación.")
        self.write("El instalador actual está fijado a clienteafirma v1.9.2.")
        self.write("Primero se consultan las versiones con la tarjeta 'Versiones'.")
        self.write("Cuando se defina el nuevo flujo de actualización, esta acción podrá reutilizar el mismo instalador.")

    def versions(self):
        self.run_pty("Consultar versiones oficiales", [
            "bash", "-lc",
            "echo 'Tags recientes de clienteafirma:'; "
            "git ls-remote --tags https://github.com/ctt-gob-es/clienteafirma.git "
            "| grep -v '\\^{}' | tail -10"
        ])

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
