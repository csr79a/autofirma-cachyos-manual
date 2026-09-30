
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

Las operaciones ejecutadas mediante PTY pueden cancelarse de forma progresiva:
primero se envía Ctrl+C por el PTY y, si el proceso no termina, una segunda
pulsación termina el grupo de procesos. Cancelar no deshace cambios que ya
haya realizado una instalación. La GUI evita recolectar dos veces el mismo
proceso y conserva correctamente un código de salida 0.

# Manual: Compilar e instalar AutoFirma desde código fuente en CachyOS (Arch Linux)

Validado en una instalación limpia de CachyOS dentro de una VM de Proxmox, agosto de 2026.

Este manual compila `clienteafirma` (el repositorio oficial del Gobierno de España) siguiendo exactamente el mismo proceso que usa el paquete `autofirma` del AUR (mantenido por `ogarcia`), pero sin pasar por AUR ni por ningún helper como `yay`.

---

## 0. Requisitos previos

- CachyOS (o cualquier Arch Linux) con acceso a `sudo`
- Conexión a internet
- Un certificado digital personal en formato `.pfx` o `.p12` (por ejemplo, FNMT), si más adelante se quiere probar la firma real

---


## Cambios de seguridad y reproducibilidad del instalador

El instalador se ejecuta como usuario normal. Si se ejecuta como root, termina
antes de realizar cambios. Las operaciones administrativas se hacen mediante
sudo.

Las referencias utilizadas por el instalador están fijadas:

- clienteafirma: v1.9.2;
- Java-WebSocket:
  8c5766a293c2dd3e0d035c0e0d70f88f57235fa8;
- ficheros de integración de ogarcia/pkgbuilds:
  de4c5a562a769357e9a78f00add6e32cd32aed40.

Antes de compilar cada repositorio se ejecuta:

```bash
git fetch --all --tags --prune
git checkout --force <referencia>
git clean -fdx
```

El parche del PR #487 está dentro del repositorio en:

```
patches/487.patch
```

No se descarga durante la instalación. El instalador utiliza primero
`git apply --check`. Si el parche ya está aplicado, lo detecta con
`git apply -R --check`. Cualquier otro estado provoca un error y detiene la
compilación.

Los ficheros externos de integración se descargan con `curl -fsSL` y desde
una URL que contiene el commit fijado. Así, un error HTTP no termina instalado
como si fuera un fichero correcto.

### Java

El instalador instala JDK 17 y utiliza temporalmente:

```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
export PATH="$JAVA_HOME/bin:$PATH"
```

No utiliza `archlinux-java set`, por lo que no cambia el Java predeterminado
del sistema.

### Fallos y reanudación

El directorio `~/build/autofirma` se conserva si la instalación falla. El
mensaje final indica dónde está el árbol de trabajo para poder diagnosticarlo
o reanudarlo.

## Firefox Flatpak

Si está instalado `org.mozilla.firefox`, el instalador muestra un aviso. El
Firefox Flatpak no utiliza el fichero del sistema:

```
/usr/lib/firefox/defaults/pref/autofirma.js
```

La GUI busca además perfiles en:

```
~/.var/app/org.mozilla.firefox/.mozilla/firefox
```

La acción de confianza de navegadores trabaja con perfiles que contienen
`cert9.db`.

## GUI: contraseña y procesos

La GUI utiliza un PTY real para el instalador. Cuando detecta una petición de
`password`, `contraseña` o `clave`, cambia temporalmente el campo inferior
a modo contraseña. Después de enviar la entrada vuelve a mostrar un campo
normal.

La cancelación es progresiva:

1. primera pulsación: escribe Ctrl+C en el PTY;
2. segunda pulsación rápida: usa `SIGKILL` sobre el grupo de procesos.

El código de lectura espera a recoger al hijo una sola vez. Si el PTY alcanza
EOF antes de que `waitpid` devuelva el estado, la GUI espera a disponer del
estado real en lugar de convertir un proceso correctamente terminado en código
130.

## NSS

La comprobación de NSS crea el directorio con:

```text
~/.pki/nssdb
```

antes de ejecutar `certutil -N` cuando el almacén no existe. Después comprueba
la presencia de `cert9.db`.

Un almacén existente no se borra ni se reinicializa.

## Certificados PKCS#12

La GUI acepta `.p12` y `.pfx`. Para leer la información del certificado:

- calcula la huella SHA-256;
- muestra `notBefore`;
- muestra `notAfter`;
- avisa si parece caducado, sin bloquear la importación;
- con OpenSSL 3, reintenta con `-legacy` si el primer intento falla.

La contraseña no se guarda en la configuración.

## Versiones

La consulta de versiones utiliza:

```bash
git ls-remote --tags --refs --sort=v:refname   https://github.com/ctt-gob-es/clienteafirma.git | tail -10
```

Así se ordenan los tags por versión antes de seleccionar los últimos.

## Registro y comodidad de la GUI

La GUI incluye:

- Guardar log;
- Limpiar log;
- recuerdo del último directorio de certificados mediante QSettings;
- reconocimiento de `AutoFirma_ROOT.cer`, `AutoFirma_ROOT.pem` y variantes de
  mayúsculas/minúsculas;
- búsqueda robusta del instalador desde la propia estructura del repositorio.

