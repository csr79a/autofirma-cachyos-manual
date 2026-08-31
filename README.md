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
