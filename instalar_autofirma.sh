#!/usr/bin/env bash
#
# instalar_autofirma.sh
#
# Automatiza la compilación e instalación de AutoFirma desde código fuente
# en CachyOS / Arch Linux, siguiendo el manual:
#   Manual_AutoFirma_CachyOS_Compilacion.md
#
# Uso:
#   chmod +x instalar_autofirma.sh
#   ./instalar_autofirma.sh
#
# Si ~/.pki/nssdb ya existe, este script NO lo recrea, NO lo borra y NO lo modifica.

set -euo pipefail

echo "Este equipo, ¿es un entorno de referencia donde harás futuras"
echo "actualizaciones (conservar código fuente y caché de compilación),"
echo "o es un equipo de uso personal donde solo quieres AutoFirma"
echo "instalado, sin dejar carpetas de compilación?"
read -rp "¿Eliminar las carpetas de compilación al finalizar? [y/N] " resp_clean
CLEAN_AFTER=false
if [[ "$resp_clean" =~ ^[Yy]$ ]]; then
    CLEAN_AFTER=true
fi

BUILD_DIR="$HOME/build/autofirma"
JAVA_WEBSOCKET_COMMIT="8c5766a293c2dd3e0d035c0e0d70f88f57235fa8"
CLIENTEAFIRMA_TAG="v1.9.2"
PATCH_URL="https://patch-diff.githubusercontent.com/raw/ctt-gob-es/clienteafirma/pull/487.patch"
PKGBUILDS_BASE="https://raw.githubusercontent.com/ogarcia/pkgbuilds/master/autofirma"
NSS_DIR="$HOME/.pki/nssdb"

log() {
    echo -e "\n\033[1;34m==> $1\033[0m"
}

log "1. Instalando JDK 17 y Maven"
sudo pacman -S --needed --noconfirm jdk17-openjdk maven git curl patch xdg-utils nss

if ! archlinux-java status | grep -q "java-17-openjdk (default)"; then
    log "Fijando JDK 17 como entorno activo"
    sudo archlinux-java set java-17-openjdk
fi
archlinux-java status

log "2. Compilando Java-WebSocket (parche del issue #320)"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
if [ ! -d "Java-WebSocket" ]; then
    git clone https://github.com/TooTallNate/Java-WebSocket.git
fi
cd Java-WebSocket
git fetch --all
git checkout "$JAVA_WEBSOCKET_COMMIT"
mvn clean install -Dmaven.test.skip=true

log "3. Clonando clienteafirma y aplicando el parche del PR #487"
cd "$BUILD_DIR"
if [ ! -d "clienteafirma" ]; then
    git clone https://github.com/ctt-gob-es/clienteafirma.git
fi
cd clienteafirma
git fetch --all
git checkout "$CLIENTEAFIRMA_TAG"

curl -L -o ../487.patch "$PATCH_URL"

if patch -p1 --dry-run < ../487.patch > /dev/null 2>&1; then
    patch -p1 < ../487.patch
    log "Parche del PR #487 aplicado correctamente"
else
    echo "AVISO: el parche del PR #487 no encaja limpio (posible ya aplicado"
    echo "en esta versión, o el repositorio oficial avanzó). Revisa a mano"
    echo "el archivo $BUILD_DIR/487.patch antes de continuar."
    read -rp "¿Continuar sin aplicar el parche? [y/N] " respuesta
    if [[ ! "$respuesta" =~ ^[Yy]$ ]]; then
        echo "Abortando."
        exit 1
    fi
fi

log "4. Compilando clienteafirma"
mvn clean install -Denv=install -Dmaven.test.skip=true

JAR_PATH="$BUILD_DIR/clienteafirma/afirma-simple/target/autofirma.jar"
if [ ! -f "$JAR_PATH" ]; then
    echo "ERROR: no se encontró el jar compilado en $JAR_PATH"
    exit 1
fi

log "5. Descargando los ficheros de soporte del paquete"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
curl -sL -o "$TMP_DIR/autofirma" "$PKGBUILDS_BASE/autofirma"
curl -sL -o "$TMP_DIR/autofirma.desktop" "$PKGBUILDS_BASE/autofirma.desktop"
curl -sL -o "$TMP_DIR/autofirma.js" "$PKGBUILDS_BASE/autofirma.js"
curl -sL -o "$TMP_DIR/autofirma.svg" "$PKGBUILDS_BASE/autofirma.svg"

log "6. Instalando en el sistema"
sudo install -Dm755 "$TMP_DIR/autofirma" /usr/bin/autofirma
sudo install -Dm644 "$TMP_DIR/autofirma.js" /usr/lib/firefox/defaults/pref/autofirma.js
sudo install -Dm644 "$JAR_PATH" /usr/share/java/autofirma/autofirma.jar
sudo install -Dm644 "$TMP_DIR/autofirma.svg" /usr/share/pixmaps/autofirma.svg
sudo install -Dm644 "$TMP_DIR/autofirma.desktop" /usr/share/applications/autofirma.desktop

log "7. Registrando el protocolo afirma://"
xdg-mime default autofirma.desktop x-scheme-handler/afirma
echo "Protocolo registrado: $(xdg-mime query default x-scheme-handler/afirma)"

log "8. Comprobando el almacén NSS"
if [ -d "$NSS_DIR" ]; then
    echo "El almacén NSS ya existe en $NSS_DIR."
    echo "NO se recrea, NO se borra y NO se modifica."
    if ! certutil -L -d "sql:$NSS_DIR" > /dev/null 2>&1; then
        echo "AVISO: certutil no puede abrir el almacén existente."
        echo "No se ha tocado el almacén. Revísalo desde la GUI o manualmente."
    else
        echo "Almacén NSS existente: válido y preservado."
    fi
else
    log "Creando un almacén NSS nuevo (vacío, sin contraseña)"
    mkdir -p "$NSS_DIR"
    certutil -N -d "sql:$NSS_DIR" --empty-password
    chmod 700 "$NSS_DIR"
    echo "Almacén NSS creado en $NSS_DIR con contraseña vacía."
fi

log "9. Limpieza de carpetas de compilación"
if [ "$CLEAN_AFTER" = true ]; then
    echo "Eliminando carpetas de compilación."
    rm -rf "$BUILD_DIR"
    BUILD_PARENT="$(dirname "$BUILD_DIR")"
    if [ -d "$BUILD_PARENT" ] && [ -z "$(ls -A "$BUILD_PARENT" 2>/dev/null)" ]; then
        rmdir "$BUILD_PARENT"
    fi
    rm -rf "$HOME/.m2/repository/org/java-websocket"
    echo "Carpetas de compilación eliminadas."
    echo "Nota: jdk17-openjdk y maven NO se desinstalan."
else
    echo "Se conserva $BUILD_DIR y el caché de Maven para futuras recompilaciones."
fi

log "Instalación completada"
cat <<'EOF'

Siguientes pasos:
  - Arranca AutoFirma una vez con: autofirma
    Esto genera ~/.afirma/Autofirma/AutoFirma_ROOT.cer y el material
    interno necesario para el socket local.
  - Usa la GUI del repositorio para:
      1) comprobar/crear ~/.pki/nssdb (sin contraseña),
      2) importar tu certificado .p12/.pfx,
      3) confiar AutoFirma ROOT en los almacenes NSS de navegador.
  - En AutoFirma → Preferencias → Almacenes de claves:
      Almacén por defecto: NSS
      Usar también en las llamadas a Autofirma desde el navegador
  - Prueba la integración en:
      https://expinterweb.mites.gob.es/scriptAutofirmaTest/

Consulta Manual_AutoFirma_CachyOS_Compilacion.md para el detalle.
EOF
