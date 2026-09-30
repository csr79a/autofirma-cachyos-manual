# AutoFirma - Compilación desde código fuente en CachyOS

Manual para compilar e instalar AutoFirma desde el repositorio oficial
(`ctt-gob-es/clienteafirma`) en CachyOS/Arch Linux, sin depender del
paquete de AUR ni de Flatpak.

## Por qué

- Trazabilidad total: código directo del repo oficial del Gobierno,
  el PR #487 guardado localmente en `patches/487.patch`, Java-WebSocket
  fijado a un commit exacto y los ficheros de integración de `ogarcia`
  fijados a un commit concreto.
- Evita el sandboxing de Flatpak, que puede dar problemas con la
  integración NSS/navegador que necesita AutoFirma.

## Contenido

- [`Manual_AutoFirma_CachyOS_Compilacion.md`](./Manual_AutoFirma_CachyOS_Compilacion.md) —
  guía paso a paso para compilar e instalar AutoFirma en CachyOS/Arch Linux.
- [`instalar_autofirma.sh`](./instalar_autofirma.sh) — script que automatiza
  los pasos 1-8 del manual (dependencias, compilación, instalación, registro
  del protocolo y creación del almacén NSS vacío). Solo quedan a mano el
  primer arranque, la importación del certificado personal, la configuración
  de preferencias y el test final, por implicar interacción o datos
  personales.

## Uso rápido

```bash
git clone https://github.com/csr79a/autofirma-cachyos-manual.git
cd autofirma-cachyos-manual
chmod +x instalar_autofirma.sh
./instalar_autofirma.sh
```

Al arrancar, el script pregunta:

```
¿Eliminar las carpetas de compilación al finalizar? [y/N]
```

- **N** (o Enter) — para un entorno de referencia que se va a mantener
  (por ejemplo, una VM dedicada a compilar y actualizar AutoFirma):
  conserva `~/build/autofirma/` y el caché de Maven, para que una
  futura actualización sea rápida (`git fetch` + recompilar, sin
  volver a clonar todo desde cero).
- **Y** — para una instalación en un equipo de uso personal, donde no
  interesa dejar carpetas de compilación ni código fuente clonado una
  vez instalado AutoFirma. Elimina `~/build/autofirma/` (y la carpeta
  padre si queda vacía) y el caché de Maven de Java-WebSocket.

En ningún caso se desinstalan `jdk17-openjdk` ni `maven`: AutoFirma
necesita el JDK 17 también en tiempo de ejecución, no solo para
compilar, así que quitarlo rompería la aplicación ya instalada.

Tras ejecutar el script, sigue el manual desde el paso 8 (primer
arranque) para completar la instalación.

## Comprobar si hay una versión nueva de AutoFirma

```bash
git ls-remote --tags https://github.com/ctt-gob-es/clienteafirma.git | grep -v '\^{}' | tail -5
```

O activa notificaciones en GitHub: entra a
[`ctt-gob-es/clienteafirma`](https://github.com/ctt-gob-es/clienteafirma) →
botón **Watch** → **Custom** → marca **Releases**.


## GUI de AutoFirma para CachyOS

El repositorio incluye una GUI PyQt6 en `gui/autofirma_cachyos_gui.py`, con el mismo enfoque de PTY, salida interactiva, tarjetas y cancelación usado en las otras GUI del proyecto.

Instala la dependencia gráfica:

```bash
sudo pacman -S --needed python python-pyqt6
```

Ejecuta **sin sudo**:

```bash
python3 gui/autofirma_cachyos_gui.py
```

La GUI ofrece:

1. **Instalar / reconstruir AutoFirma** — ejecuta el instalador existente; no duplica la lógica de compilación.
2. **NSS** — crea `~/.pki/nssdb` con contraseña vacía si no existe. Si ya existe, no lo recrea, no lo borra y no lo modifica.
3. **Certificado** — selector gráfico para `.p12/.pfx`, comprobación de contraseña y huella SHA-256, detección de duplicado e importación segura con `pk12util`.
4. **Navegadores** — confía en `AutoFirma ROOT` en el NSS compartido y en perfiles Firefox con `cert9.db`, cuando existen.
5. **Estado** — comprueba dependencias, JAR, NSS, CA local y protocolo `afirma://`.
6. **Versiones** — consulta los tags publicados por `ctt-gob-es/clienteafirma` sin modificar la instalación.
7. **Actualizar AutoFirma** — botón preparado, actualmente informativo; no modifica la instalación porque el flujo de actualización aún no está definido.

La GUI **no inventa un mecanismo de actualización distinto al instalador**: la instalación/reconstrucción sigue usando el flujo CachyOS/Arch documentado.



## Reproducibilidad y endurecimiento

El instalador no debe ejecutarse como root. Usa sudo solo para las operaciones
que requieren privilegios.

Las referencias de compilación están fijadas:

- clienteafirma: `v1.9.2`;
- Java-WebSocket: `8c5766a293c2dd3e0d035c0e0d70f88f57235fa8`;
- ficheros de integración de `ogarcia/pkgbuilds`: commit
  `de4c5a562a769357e9a78f00add6e32cd32aed40`.

El PR #487 se conserva en `patches/487.patch` y se valida con
`git apply --check` antes de aplicarlo. Si ya está aplicado, el instalador lo
detecta con `git apply -R --check`.

Los repositorios de compilación se sincronizan con `git fetch --all --tags
--prune`, `git checkout --force` y `git clean -fdx` antes de compilar.

Las descargas utilizan `curl -fsSL`, de modo que un error HTTP no se trata
como si fuera un fichero válido.

El JDK 17 se selecciona mediante `JAVA_HOME` y `PATH` dentro del proceso
del instalador; no se cambia el Java predeterminado del sistema.

Si una compilación falla, `~/build/autofirma` se conserva para poder revisar
el estado y reanudar el trabajo.

## Cambios de la GUI

La GUI utiliza `shutil.which()`, detección de contraseñas en la salida del
PTY y campos ocultos cuando solicita una clave. La cancelación envía primero
Ctrl+C por el PTY y, en una segunda pulsación, termina el grupo de procesos.

La consulta de versiones utiliza ordenación semántica de tags. La búsqueda de
perfiles Firefox incluye la ubicación de Firefox Flatpak.

La importación PKCS#12 muestra la vigencia del certificado y prueba el modo
`-legacy` de OpenSSL 3 cuando es necesario. La GUI también recuerda el último
directorio de certificados, permite guardar/limpiar el log y reconoce varias
variantes del nombre de `AutoFirma ROOT`.

