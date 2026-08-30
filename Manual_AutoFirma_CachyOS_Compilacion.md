# Manual: Compilar e instalar AutoFirma desde código fuente en CachyOS (Arch Linux)

Validado en una instalación limpia de CachyOS dentro de una VM de Proxmox, agosto de 2026.

Este manual compila `clienteafirma` (el repositorio oficial del Gobierno de España) siguiendo exactamente el mismo proceso que usa el paquete `autofirma` del AUR (mantenido por `ogarcia`), pero sin pasar por AUR ni por ningún helper como `yay`.

---

## 0. Requisitos previos

- CachyOS (o cualquier Arch Linux) con acceso a `sudo`
- Conexión a internet
- Un certificado digital personal en formato `.pfx` o `.p12` (por ejemplo, FNMT), si más adelante se quiere probar la firma real

---

## 1. Instalar JDK 17 y Maven

AutoFirma 1.9.2 se compila con **JDK 17** (no con la 11, a pesar de que algunos comentarios antiguos del AUR lo sugieran — el PKGBUILD actual fija explícitamente `java-environment=17`).

```bash
sudo pacman -S --needed jdk17-openjdk maven git
```

Si el sistema tiene varias versiones de Java instaladas, comprobar cuál es la activa:

```bash
archlinux-java status
```

Si `java-17-openjdk` no aparece como `(default)`, fijarla:

```bash
sudo archlinux-java set java-17-openjdk
```

Verificar:

```bash
archlinux-java status
# Available Java environments:
#   java-17-openjdk (default)
```

---

## 2. Compilar la dependencia Java-WebSocket (parche del issue #320)

AutoFirma necesita una versión concreta de la librería `Java-WebSocket`, que **no forma parte del repositorio de `clienteafirma`**, sino de un proyecto aparte (`TooTallNate/Java-WebSocket`). Hay que clonarla, fijar el commit exacto y compilarla e instalarla en el repositorio Maven local (`~/.m2`) para que `clienteafirma` la encuentre luego como dependencia.

Para no dejar los repositorios clonados sueltos en `$HOME`, se agrupan en `~/build/autofirma/`. Esto también facilita una futura actualización: si sale una versión nueva de AutoFirma, basta con entrar en esta carpeta, hacer `git fetch` y recompilar, sin tener que volver a clonar ni buscar de nuevo el commit exacto de Java-WebSocket.

```bash
mkdir -p ~/build/autofirma
cd ~/build/autofirma
git clone https://github.com/TooTallNate/Java-WebSocket.git
cd Java-WebSocket
git checkout 8c5766a293c2dd3e0d035c0e0d70f88f57235fa8
mvn clean install -Dmaven.test.skip=true
```

Al finalizar debe aparecer `BUILD SUCCESS`. Esto instala `Java-WebSocket-1.6.1-SNAPSHOT` en `~/.m2/repository/org/java-websocket/`.

---

## 3. Clonar clienteafirma y aplicar el parche del PR #487

```bash
cd ~/build/autofirma
git clone https://github.com/ctt-gob-es/clienteafirma.git
cd clienteafirma
git checkout v1.9.2
```

Descargar el patch del PR #487 (corrige la detección del perfil de Firefox según el estándar XDG — issue #479):

```bash
curl -L -o ../487.patch https://patch-diff.githubusercontent.com/raw/ctt-gob-es/clienteafirma/pull/487.patch
```

> **Nota:** como el comando se ejecuta desde `~/build/autofirma/clienteafirma/`, el patch queda guardado en `~/build/autofirma/487.patch`. Esta carpeta ya existe en este punto porque se creó con el `mkdir -p` del paso 2.

Comprobar que el patch encaja limpio antes de aplicarlo:

```bash
patch -p1 --dry-run < ../487.patch
```

Si no hay errores, aplicarlo de verdad:

```bash
patch -p1 < ../487.patch
```

---

## 4. Compilar clienteafirma

Desde la raíz del repositorio (`~/build/autofirma/clienteafirma`), con JDK 17 como entorno activo:

```bash
mvn clean install -Denv=install -Dmaven.test.skip=true
```

La compilación tarda unos minutos. Al finalizar debe verse:

```
[INFO] BUILD SUCCESS
```

El artefacto final queda en:

```
afirma-simple/target/autofirma.jar
```

(y opcionalmente `afirma-ui-simple-configurator/target/autofirmaConfigurador.jar`, el configurador de integración con navegadores)

---

## 5. Descargar los ficheros de soporte del paquete

El paquete real incluye, además del `.jar`, un script lanzador, un `.desktop`, un icono y una preferencia para Firefox. Están alojados en el repositorio de PKGBUILDs del mantenedor:

```bash
cd /tmp
curl -sL -o autofirma https://raw.githubusercontent.com/ogarcia/pkgbuilds/master/autofirma/autofirma
curl -sL -o autofirma.desktop https://raw.githubusercontent.com/ogarcia/pkgbuilds/master/autofirma/autofirma.desktop
curl -sL -o autofirma.js https://raw.githubusercontent.com/ogarcia/pkgbuilds/master/autofirma/autofirma.js
curl -sL -o autofirma.svg https://raw.githubusercontent.com/ogarcia/pkgbuilds/master/autofirma/autofirma.svg
```

El script lanzador (`autofirma`) ya incluye lógica propia para generar un certificado CA local (para el socket interno de AutoFirma) y para localizar el JDK 17 automáticamente.

---

## 6. Instalar en el sistema

```bash
sudo install -Dm755 /tmp/autofirma /usr/bin/autofirma
sudo install -Dm644 /tmp/autofirma.js /usr/lib/firefox/defaults/pref/autofirma.js
sudo install -Dm644 ~/build/autofirma/clienteafirma/afirma-simple/target/autofirma.jar /usr/share/java/autofirma/autofirma.jar
sudo install -Dm644 /tmp/autofirma.svg /usr/share/pixmaps/autofirma.svg
sudo install -Dm644 /tmp/autofirma.desktop /usr/share/applications/autofirma.desktop
```

---

## 7. Registrar el protocolo `afirma://`

Necesario para que las páginas web puedan invocar AutoFirma directamente:

```bash
xdg-mime default autofirma.desktop x-scheme-handler/afirma
```

Verificar:

```bash
xdg-mime query default x-scheme-handler/afirma
# → autofirma.desktop
```

---

## 8. Primer arranque

```bash
autofirma
```

En el primer arranque, el script genera automáticamente un CA local en `~/.afirma/Autofirma/` y lo registra en el almacén NSS y en el perfil de Firefox detectado (si existe). Este certificado es interno, solo para el mecanismo de socket de AutoFirma — no tiene relación con el certificado personal del usuario.

---

## 9. Importar el certificado personal (FNMT u otro)

Para que AutoFirma pueda firmar de verdad, el certificado personal debe estar en el almacén NSS compartido del sistema (`~/.pki/nssdb`).

> Si usaste `instalar_autofirma.sh`, el almacén ya está creado (vacío,
> sin contraseña) y puedes saltar directamente al paso de importación
> del certificado.

Crear el almacén con **contraseña en blanco** (crítico: una contraseña no vacía provoca fallos silenciosos cuando el navegador invoca la firma):

```bash
mkdir -p ~/.pki/nssdb
certutil -N -d sql:$HOME/.pki/nssdb --empty-password
```

Importar el certificado personal (`.pfx`/`.p12`):

```bash
pk12util -d sql:$HOME/.pki/nssdb -i /ruta/al/certificado.pfx
```

Verificar que se importó correctamente:

```bash
certutil -L -d sql:$HOME/.pki/nssdb
```

Debe listar el certificado personal junto con las CA correspondientes (por ejemplo, para FNMT: `AC RAIZ FNMT-RCM` y `AC FNMT Usuarios`).

---

## 10. Configurar AutoFirma para usar NSS desde el navegador

Abrir AutoFirma → **Preferencias** → pestaña **Almacenes de claves**:

- Almacén por defecto: **NSS**
- Marcar **"Usar también en las llamadas a Autofirma desde el navegador"**

---

## 11. Probar la integración completa

Con Firefox instalado y un perfil ya creado (abrirlo una vez es suficiente), visitar una página de verificación oficial, por ejemplo:

**https://expinterweb.mites.gob.es/scriptAutofirmaTest/**

Esta página comprueba automáticamente:
- Navegador compatible
- Sistema operativo compatible
- Que AutoFirma responde al protocolo `afirma://`

Y permite lanzar un **test de firma real** (CAdES y XAdES) contra el certificado importado. Un resultado en verde ("Correcto") en ambos formatos confirma que toda la cadena funciona: **web → protocolo `afirma://` → AutoFirma → almacén NSS → certificado personal → firma**.

---

## Resumen de rutas y comandos clave

| Elemento | Ruta / comando |
|---|---|
| JDK requerido | `jdk17-openjdk` |
| Repo Java-WebSocket (parche #320) | `TooTallNate/Java-WebSocket` @ `8c5766a293c2dd3e0d035c0e0d70f88f57235fa8` |
| Patch PR #487 | `https://patch-diff.githubusercontent.com/raw/ctt-gob-es/clienteafirma/pull/487.patch` |
| Comando de build | `mvn clean install -Denv=install -Dmaven.test.skip=true` |
| Directorio de trabajo (repos clonados) | `~/build/autofirma/` |
| Jar final | `~/build/autofirma/clienteafirma/afirma-simple/target/autofirma.jar` |
| Ficheros de soporte | `ogarcia/pkgbuilds/autofirma/` (GitHub) |
| Almacén de certificados | `~/.pki/nssdb` (contraseña en blanco) |
| Página de test oficial | `https://expinterweb.mites.gob.es/scriptAutofirmaTest/` |
