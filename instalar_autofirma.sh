#!/usr/bin/env bash
#
# instalar_autofirma.sh
#
# Automatiza la compilación e instalación de AutoFirma desde código fuente
# en CachyOS / Arch Linux, siguiendo el manual:
#   Manual_AutoFirma_CachyOS_Compilacion.md
#
# Repositorio: https://github.com/csr79a/autofirma-cachyos-manual
#
# Uso:
#   chmod +x instalar_autofirma.sh
#   ./instalar_autofirma.sh
#
# El script se detiene ante cualquier error (set -e) para no dejar
# el sistema en un estado a medias.

set -euo pipefail

BUILD_DIR="$HOME/build/autofirma"
JAVA_WEBSOCKET_COMMIT="8c5766a293c2dd3e0d035c0e0d70f88f57235fa8"
CLIENTEAFIRMA_TAG="v1.9.2"
PATCH_URL="https://patch-diff.githubusercontent.com/raw/ctt-gob-es/clienteafirma/pull/487.patch"
PKGBUILDS_BASE="https://raw.githubusercontent.com/ogarcia/pkgbuilds/master/autofirma"

log() {
    echo -e "\n\033[1;34m==> $1\033[0m"
}

# ---------------------------------------------------------------------------
log "1. Instalando JDK 17 y Maven"
# ---------------------------------------------------------------------------
sudo pacman -S --needed --noconfirm jdk17-openjdk maven git

if ! archlinux-java status | grep -q "java-17-openjdk (default)"; then
    log "Fijando JDK 17 como entorno activo"
    sudo archlinux-java set java-17-openjdk
fi
archlinux-java status

# ---------------------------------------------------------------------------
log "2. Compilando Java-WebSocket (parche del issue #320)"
# ---------------------------------------------------------------------------
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

if [ ! -d "Java-WebSocket" ]; then
    git clone https://github.com/TooTallNate/Java-WebSocket.git
fi
cd Java-WebSocket
git fetch --all
git checkout "$JAVA_WEBSOCKET_COMMIT"
mvn clean install -Dmaven.test.skip=true

# ---------------------------------------------------------------------------
log "3. Clonando clienteafirma y aplicando el parche del PR #487"
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
log "4. Compilando clienteafirma"
# ---------------------------------------------------------------------------
mvn clean install -Denv=install -Dmaven.test.skip=true

JAR_PATH="$BUILD_DIR/clienteafirma/afirma-simple/target/autofirma.jar"
if [ ! -f "$JAR_PATH" ]; then
    echo "ERROR: no se encontró el jar compilado en $JAR_PATH"
    exit 1
fi

# ---------------------------------------------------------------------------
log "5. Descargando los ficheros de soporte del paquete"
# ---------------------------------------------------------------------------
TMP_DIR="$(mktemp -d)"
curl -sL -o "$TMP_DIR/autofirma" "$PKGBUILDS_BASE/autofirma"
curl -sL -o "$TMP_DIR/autofirma.desktop" "$PKGBUILDS_BASE/autofirma.desktop"
curl -sL -o "$TMP_DIR/autofirma.js" "$PKGBUILDS_BASE/autofirma.js"
curl -sL -o "$TMP_DIR/autofirma.svg" "$PKGBUILDS_BASE/autofirma.svg"

# ---------------------------------------------------------------------------
log "6. Instalando en el sistema"
# ---------------------------------------------------------------------------
sudo install -Dm755 "$TMP_DIR/autofirma" /usr/bin/autofirma
sudo install -Dm644 "$TMP_DIR/autofirma.js" /usr/lib/firefox/defaults/pref/autofirma.js
sudo install -Dm644 "$JAR_PATH" /usr/share/java/autofirma/autofirma.jar
sudo install -Dm644 "$TMP_DIR/autofirma.svg" /usr/share/pixmaps/autofirma.svg
sudo install -Dm644 "$TMP_DIR/autofirma.desktop" /usr/share/applications/autofirma.desktop

rm -rf "$TMP_DIR"

# ---------------------------------------------------------------------------
log "7. Registrando el protocolo afirma://"
# ---------------------------------------------------------------------------
xdg-mime default autofirma.desktop x-scheme-handler/afirma
echo "Protocolo registrado: $(xdg-mime query default x-scheme-handler/afirma)"

# ---------------------------------------------------------------------------
log "Instalación completada"
# ---------------------------------------------------------------------------
cat <<'EOF'

Pasos que quedan por hacer A MANO (no automatizados por este script,
por implicar interacción o datos personales):

  8. Primer arranque:
       autofirma
     (genera el CA local en ~/.afirma/Autofirma/)

  9. Importar tu certificado personal (FNMT u otro) en el almacén NSS:
       mkdir -p ~/.pki/nssdb
       certutil -N -d sql:$HOME/.pki/nssdb --empty-password
       pk12util -d sql:$HOME/.pki/nssdb -i /ruta/a/tu/certificado.pfx
       certutil -L -d sql:$HOME/.pki/nssdb

  10. En AutoFirma → Preferencias → Almacenes de claves:
        - Almacén por defecto: NSS
        - Marcar "Usar también en las llamadas a Autofirma desde el navegador"

  11. Probar la integración completa en:
        https://expinterweb.mites.gob.es/scriptAutofirmaTest/

Consulta el manual completo (Manual_AutoFirma_CachyOS_Compilacion.md)
para el detalle de cada paso.
EOF
