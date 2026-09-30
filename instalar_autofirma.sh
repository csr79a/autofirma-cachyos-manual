#!/usr/bin/env bash
#
# instalar_autofirma.sh
#
# Automatiza la compilación e instalación de AutoFirma desde código fuente
# en CachyOS / Arch Linux.
#
# Uso:
#   chmod +x instalar_autofirma.sh
#   ./instalar_autofirma.sh
#
# Se ejecuta como usuario normal y usa sudo solo cuando es necesario.
# Si ~/.pki/nssdb ya existe, NO se recrea, NO se borra y NO se modifica.

set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
    echo "ERROR: no ejecutes este script como root." >&2
    echo "Ejecuta: ./instalar_autofirma.sh" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$HOME/build/autofirma"
JAVA_WEBSOCKET_COMMIT="8c5766a293c2dd3e0d035c0e0d70f88f57235fa8"
CLIENTEAFIRMA_TAG="v1.9.2"
PATCH_FILE="$SCRIPT_DIR/patches/487.patch"
PKGBUILDS_COMMIT="de4c5a562a769357e9a78f00add6e32cd32aed40"
PKGBUILDS_BASE="https://raw.githubusercontent.com/ogarcia/pkgbuilds/$PKGBUILDS_COMMIT/autofirma"
NSS_DIR="$HOME/.pki/nssdb"
TMP_DIR=""

log() {
    printf '\n\033[1;34m==> %s\033[0m\n' "$1"
}

cleanup() {
    local status=$?
    if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
        rm -rf "$TMP_DIR"
    fi
    if [[ $status -ne 0 && -d "$BUILD_DIR" ]]; then
        printf '\nAVISO: la instalación terminó con error (código %s).\n' "$status" >&2
        printf 'Se conserva %s para poder revisar o reanudar la compilación.\n' "$BUILD_DIR" >&2
    fi
    exit "$status"
}
trap cleanup EXIT

printf '%s\n' "Este equipo, ¿es un entorno de referencia donde harás futuras"
printf '%s\n' "actualizaciones (conservar código fuente y caché de compilación),"
printf '%s\n' "o es un equipo de uso personal donde solo quieres AutoFirma"
printf '%s\n' "instalado, sin dejar carpetas de compilación?"
read -rp "¿Eliminar las carpetas de compilación al finalizar? [y/N] " resp_clean || true
CLEAN_AFTER=false
if [[ "$resp_clean" =~ ^[Yy]$ ]]; then
    CLEAN_AFTER=true
fi

sync_repo() {
    local dir="$1"
    local ref="$2"
    local url="$3"

    if [[ ! -d "$dir/.git" ]]; then
        rm -rf "$dir"
        git clone "$url" "$dir"
    fi
    cd "$dir"
    git fetch --all --tags --prune
    git checkout --force "$ref"
    git clean -fdx
}

apply_local_patch() {
    local patch_file="$1"

    if [[ ! -f "$patch_file" ]]; then
        echo "ERROR: no se encuentra el parche local: $patch_file" >&2
        exit 1
    fi

    if git apply --check "$patch_file" >/dev/null 2>&1; then
        git apply "$patch_file"
        log "Parche del PR #487 aplicado correctamente"
    elif git apply -R --check "$patch_file" >/dev/null 2>&1; then
        log "El parche del PR #487 ya estaba aplicado; no se vuelve a aplicar"
    else
        echo "ERROR: el parche del PR #487 no se puede aplicar de forma limpia." >&2
        echo "Revisa la versión de clienteafirma y $patch_file." >&2
        exit 1
    fi
}

log "1. Instalando JDK 17, Maven y herramientas necesarias"
sudo pacman -S --needed --noconfirm jdk17-openjdk maven git curl patch xdg-utils nss openssl

if [[ ! -d /usr/lib/jvm/java-17-openjdk ]]; then
    echo "ERROR: no se encuentra /usr/lib/jvm/java-17-openjdk después de instalar JDK 17." >&2
    exit 1
fi
export JAVA_HOME="/usr/lib/jvm/java-17-openjdk"
export PATH="$JAVA_HOME/bin:$PATH"
printf 'JAVA_HOME temporal para la compilación: %s\n' "$JAVA_HOME"
java -version

log "2. Compilando Java-WebSocket (parche del issue #320)"
mkdir -p "$BUILD_DIR"
sync_repo "$BUILD_DIR/Java-WebSocket" "$JAVA_WEBSOCKET_COMMIT" "https://github.com/TooTallNate/Java-WebSocket.git"
mvn clean install -Dmaven.test.skip=true

log "3. Clonando clienteafirma y aplicando el parche del PR #487"
sync_repo "$BUILD_DIR/clienteafirma" "$CLIENTEAFIRMA_TAG" "https://github.com/ctt-gob-es/clienteafirma.git"
apply_local_patch "$PATCH_FILE"

log "4. Compilando clienteafirma"
mvn clean install -Denv=install -Dmaven.test.skip=true

JAR_PATH="$BUILD_DIR/clienteafirma/afirma-simple/target/autofirma.jar"
if [[ ! -f "$JAR_PATH" ]]; then
    echo "ERROR: no se encontró el jar compilado en $JAR_PATH" >&2
    exit 1
fi

log "5. Descargando los ficheros de soporte del paquete"
TMP_DIR="$(mktemp -d)"
curl -fsSL -o "$TMP_DIR/autofirma" "$PKGBUILDS_BASE/autofirma"
curl -fsSL -o "$TMP_DIR/autofirma.desktop" "$PKGBUILDS_BASE/autofirma.desktop"
curl -fsSL -o "$TMP_DIR/autofirma.js" "$PKGBUILDS_BASE/autofirma.js"
curl -fsSL -o "$TMP_DIR/autofirma.svg" "$PKGBUILDS_BASE/autofirma.svg"

log "6. Instalando en el sistema"
sudo install -Dm755 "$TMP_DIR/autofirma" /usr/bin/autofirma
sudo install -Dm644 "$TMP_DIR/autofirma.js" /usr/lib/firefox/defaults/pref/autofirma.js
sudo install -Dm644 "$JAR_PATH" /usr/share/java/autofirma/autofirma.jar
sudo install -Dm644 "$TMP_DIR/autofirma.svg" /usr/share/pixmaps/autofirma.svg
sudo install -Dm644 "$TMP_DIR/autofirma.desktop" /usr/share/applications/autofirma.desktop

log "7. Registrando el protocolo afirma://"
xdg-mime default autofirma.desktop x-scheme-handler/afirma
printf 'Protocolo registrado: %s\n' "$(xdg-mime query default x-scheme-handler/afirma)"

if command -v flatpak >/dev/null 2>&1 && flatpak list --app --columns=application 2>/dev/null | grep -Fxq 'org.mozilla.firefox'; then
    echo "AVISO: se detectó Firefox Flatpak (org.mozilla.firefox)."
    echo "Firefox Flatpak no lee /usr/lib/firefox/defaults/pref/autofirma.js."
    echo "La confianza de AutoFirma ROOT debe configurarse en su perfil NSS."
fi

log "8. Comprobando el almacén NSS"
if [[ -d "$NSS_DIR" ]]; then
    echo "El almacén NSS ya existe en $NSS_DIR."
    echo "NO se recrea, NO se borra y NO se modifica."
    if ! certutil -L -d "sql:$NSS_DIR" >/dev/null 2>&1; then
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
if [[ "$CLEAN_AFTER" == true ]]; then
    echo "Eliminando carpetas de compilación."
    rm -rf "$BUILD_DIR"
    BUILD_PARENT="$(dirname "$BUILD_DIR")"
    if [[ -d "$BUILD_PARENT" ]] && [[ -z "$(ls -A "$BUILD_PARENT" 2>/dev/null)" ]]; then
        rmdir "$BUILD_PARENT"
    fi
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
  - Si usas Firefox Flatpak, la GUI busca también sus perfiles en:
      ~/.var/app/org.mozilla.firefox/.mozilla/firefox
  - En AutoFirma → Preferencias → Almacenes de claves:
      Almacén por defecto: NSS
      Usar también en las llamadas a Autofirma desde el navegador
  - Prueba la integración en:
      https://expinterweb.mites.gob.es/scriptAutofirmaTest/

Consulta Manual_AutoFirma_CachyOS_Compilacion.md para el detalle.
EOF
