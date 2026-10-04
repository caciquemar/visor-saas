# Decisiones

Una entrada por decisión, la más nueva arriba. Qué se decidió, por qué y qué se descartó.

## 2026-10-04 · Zicar como módulo privado de Nord Good
El conversor Polyboard → Zicar no se vende. Se integra como módulo que se prende por taller y solo está prendido
para Nord Good. Su código queda en su propio repo privado.

## 2026-10-04 · Marca propia del servicio
El servicio no usa la marca Nord Good. Cada taller pone su logo y colores en el link del cliente.

## 2026-10-04 · Conversión en el servidor
El taller sube DXF + .ocp desde el navegador y el servidor convierte. Descartado por ahora: programa de escritorio
para cada taller (instalación y versiones distintas). Puede sumarse después como "subidor".

## 2026-10-04 · Stack inicial
Django + PostgreSQL + cola de tareas + Cloudflare R2, en un VPS detrás de Cloudflare. Descartado: el NAS de la casa
para clientes pagos (cortes de luz e internet, sin respaldo de uptime).
