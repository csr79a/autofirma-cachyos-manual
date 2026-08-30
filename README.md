# AutoFirma - Compilación desde código fuente en CachyOS

Manual para compilar e instalar AutoFirma desde el repositorio oficial
(`ctt-gob-es/clienteafirma`) en CachyOS/Arch Linux, sin depender del
paquete de AUR ni de Flatpak.

## Por qué

- Trazabilidad total: código directo del repo oficial del Gobierno,
  un único parche público (PR #487), y una dependencia externa fijada
  a un commit exacto.
- Evita el sandboxing de Flatpak, que puede dar problemas con la
  integración NSS/navegador que necesita AutoFirma.

## Contenido

- [`Manual_AutoFirma_CachyOS_Compilacion.md`](./Manual_AutoFirma_CachyOS_Compilacion.md) —
  guía paso a paso para compilar e instalar AutoFirma en CachyOS/Arch Linux.
- [`instalar_autofirma.sh`](./instalar_autofirma.sh) — script que automatiza
  los pasos 1-7 del manual (compilación e instalación). Los pasos 8-11
  (arranque, importar certificado, preferencias, test) se hacen a mano
  por implicar interacción o datos personales.

## Uso rápido

```bash
git clone https://github.com/csr79a/autofirma-cachyos-manual.git
cd autofirma-cachyos-manual
chmod +x instalar_autofirma.sh
```

### Modo normal

Para un entorno de build que se va a mantener (por ejemplo, una VM
dedicada a compilar y actualizar AutoFirma), conserva las carpetas de
compilación (`~/build/autofirma/` y el caché de Maven) para que una
futura actualización sea rápida (`git fetch` + recompilar, sin volver
a clonar todo desde cero):

```bash
./instalar_autofirma.sh
```

### Modo limpio (`--clean`)

Para una instalación en un equipo de uso personal, donde no interesa
dejar carpetas de compilación ni código fuente clonado una vez
instalado AutoFirma:

```bash
./instalar_autofirma.sh --clean
```

Esto elimina `~/build/autofirma/` y el caché de Maven de
Java-WebSocket al terminar. No desinstala `jdk17-openjdk` ni `maven`
del sistema (instalados vía pacman); eso se hace a mano si no se
necesitan para nada más:

```bash
sudo pacman -Rns jdk17-openjdk maven
```

Tras ejecutar el script (en cualquiera de los dos modos), sigue el
manual desde el paso 8 para completar la instalación.
