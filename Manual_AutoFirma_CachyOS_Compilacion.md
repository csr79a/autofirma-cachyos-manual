
## GUI de AutoFirma para CachyOS

La GUI se encuentra en `gui/autofirma_cachyos_gui.py` y está diseñada con el mismo formato general que las GUI recientes del proyecto: PyQt6, PTY real, salida interactiva, entrada para preguntas/contraseñas y cancelación controlada.

### Dependencia

```bash
sudo pacman -S --needed python python-pyqt6
```

No necesita `pyte` ni una instalación de Python mediante `pip`.

### Ejecución

Desde la raíz del repositorio y **sin ejecutar la GUI como root**:

```bash
python3 gui/autofirma_cachyos_gui.py
```

### Acciones

- **Instalar / reconstruir AutoFirma**: ejecuta `instalar_autofirma.sh` con su flujo real de CachyOS. La GUI no duplica la compilación.
- **NSS**: crea `~/.pki/nssdb` solamente si no existe y lo inicializa con `certutil -N --empty-password`. Si existe, se conserva intacto; si `certutil` no puede abrirlo, se informa del problema sin recrearlo.
- **Importar certificado**: permite seleccionar gráficamente un `.p12` o `.pfx`, solicita su contraseña, obtiene la huella SHA-256, comprueba duplicados y usa `pk12util` sin guardar la contraseña.
- **Confiar en navegadores**: usa el CA interno que genera el lanzador oficial del paquete, `~/.afirma/Autofirma/AutoFirma_ROOT.cer`. Se aplica al NSS compartido cuando existe y a perfiles Firefox que contienen `cert9.db`.
- **Estado**: muestra dependencias, JAR instalado, NSS, CA local y registro de `afirma://`.
- **Versiones**: consulta los tags oficiales de `ctt-gob-es/clienteafirma`; no modifica nada.
- **Actualizar AutoFirma**: botón preparado para una futura actualización; por ahora es informativo y no modifica la instalación.

El CA `AutoFirma_ROOT.cer` **no es el certificado personal FNMT**. Es el certificado interno que AutoFirma genera para su comunicación local.

### Cancelación

Las operaciones ejecutadas mediante PTY pueden cancelarse de forma progresiva: primero se envía una interrupción equivalente a Ctrl+C y, si el proceso no termina, una segunda pulsación fuerza su finalización. Cancelar no deshace cambios que ya haya realizado una instalación.

# Manual: Compilar e instalar AutoFirma desde código fuente en CachyOS (Arch Linux)

Validado en una instalación limpia de CachyOS dentro de una VM de Proxmox, agosto de 2026.

Este manual compila `clienteafirma` (el repositorio oficial del Gobierno de España) siguiendo exactamente el mismo proceso que usa el paquete `autofirma` del AUR (mantenido por `ogarcia`), pero sin pasar por AUR ni por ningún helper como `yay`.

---

## 0. Requisitos previos

- CachyOS (o cualquier Arch Linux) con acceso a `sudo`
- Conexión a internet
- Un certificado digital personal en formato `.pfx` o `.p12` (por ejemplo, FNMT), si más adelante se quiere probar la firma real

---

