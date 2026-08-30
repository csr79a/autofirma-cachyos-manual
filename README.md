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

## Uso rápido

```bash
git clone https://github.com/csr79a/autofirma-cachyos-manual.git
```

Y sigue el manual desde el paso 1.
