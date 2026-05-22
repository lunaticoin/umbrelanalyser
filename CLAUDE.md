# Proyecto

**umbrelanalyser** — App de Umbrel que monitoriza el consumo de recursos (CPU, RAM, disco I/O, disco usage, red) de las demás apps instaladas en Umbrel, acumula datos históricos y permite exportarlos en CSV/JSON.

Caso de uso principal: comparar el consumo de una app como electrs durante indexación vs idle.

## Estado actual

- **Fase**: v1.0.0 publicado a `lunaticoin/lunaticoin-umbrel-app-store`. Pendiente de probar en un Umbrel real.
- **Última sesión**: 2026-05-22 — primer release + publicación al store comunitario
- **Última acción**: workflow `docker.yml` (run 26276474522) construyó la imagen multi-arch, digest pineado `sha256:02080b2f155205fc1c5dbf054c25fe858f6f063bf6a2e12ba12fddcc903a864d`, push hecho a ambos repos
- **Imagen**: `ghcr.io/lunaticoin/umbrelanalyser:v1.0.0`
- **Repo código**: https://github.com/lunaticoin/umbrelanalyser
- **Repo store**: https://github.com/lunaticoin/lunaticoin-umbrel-app-store (carpeta `lunaticoin-umbrelanalyser`)

## Estructura

```
umbrelanalyser/
├── CLAUDE.md
├── Dockerfile
├── requirements.txt
├── README.md
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + rutas
│   ├── db.py                # SQLite schema + queries
│   ├── docker_client.py     # Wrapper del SDK de Docker
│   ├── collector.py         # Bucle asyncio de polling
│   ├── settings.py          # Settings persistidos en DB
│   ├── export.py            # CSV/JSON
│   └── static/              # Frontend (vanilla JS + Chart.js)
├── umbrel/                  # Copia de los ficheros del app store
│   ├── umbrel-app.yml
│   ├── docker-compose.yml
│   └── exports.sh
└── .github/workflows/docker.yml  # Build multi-arch amd64+arm64
```

## Comandos

```bash
# Local dev (requiere docker socket accesible)
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 3000

# Build local
docker build -t umbrelanalyser .
docker run --rm -p 3000:3000 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v $PWD/data:/data \
  umbrelanalyser

# Build multi-arch (GHCR)
gh workflow run docker.yml -R {username}/umbrelanalyser -f version=v1.0.0
```

## Decisiones técnicas

- **Stack**: Python 3.12 + FastAPI + SQLite + Chart.js self-hosted. Vanilla JS sin bundler.
- **Polling**: cada 30s `docker stats` (CPU/RAM/blkio/net), cada 5min `du` de data-dirs. Configurable.
- **Retención**: 30 días por defecto, configurable. Pruner diario.
- **Disk usage real**: se monta `/home/umbrel/umbrel/app-data:/host-app-data:ro` para poder hacer `du` de cada app. Sin ese mount sólo trackeamos writable layer (poco útil para apps con volúmenes).
- **CPU%**: calculado a partir del delta entre dos polls consecutivos (no usamos `precpu_stats` del Docker daemon porque a veces viene a cero).
- **Auth**: delegada a Umbrel (`PROXY_AUTH_ADD: "true"`).
- **Identidad de la app**: `lunaticoin-umbrelanalyser`. Si tu GitHub es otro, cambiar `lunaticoin` por tu username en `umbrel-app.yml`, `docker-compose.yml`, workflow y todas las refs de imagen.

## Gotchas

- **Puerto 3000 está reservado por umbrelOS** — cualquier app que ponga `port: 3000` en su manifest falla al bind y la install se queda en 1%. Usamos `3737` (libre). El puerto **interno** de FastAPI sigue siendo 3000 (no rebuild). Cambiar puerto externo: editar `umbrel/umbrel-app.yml` y `port:` en el manifest del store.
- **Docker socket**: la app necesita `/var/run/docker.sock` montado read-only. Umbrel lo permite (igual que Portainer).
- **Mount de app-data parent**: el path `/home/umbrel/umbrel/app-data` es el estándar de Umbrel-on-Pi. En umbrelOS podría diferir. Si falla, ajustar el bind mount en `docker-compose.yml`.
- **CPU primera muestra**: el primer poll tras arrancar deja CPU% como `NULL` (se necesita delta). Esto es normal.
- **Network/disk I/O son cumulativos**: en la UI mostramos rates (bytes/s) computados del delta. En el export crudo guardamos cumulativo, para que el usuario pueda procesarlo como prefiera.
- **IP del bridge**: usamos `10.21.22.50`. Si choca con otra app, cambiar en `umbrel-app.yml` (no aplica), en `docker-compose.yml` y en `exports.sh`.
- **Icono**: hay que añadir `umbrel/icon.png` (512x512) antes de publicar al store. No incluido en el repo.

## Tareas pendientes

- [x] Crear `umbrel/icon.png` (512x512) — generado por `scripts/make_icon.py`
- [x] Crear repo `umbrelanalyser` en GitHub y push
- [x] Crear repo del app store comunitario (ya existía: `lunaticoin-umbrel-app-store`)
- [x] Lanzar `gh workflow run docker.yml` para construir la imagen
- [x] Pinear digest en `docker-compose.yml`
- [ ] Probar instalación en un Umbrel real (sobre todo confirmar que el mount `/home/umbrel/umbrel/app-data:ro` funciona en tu setup)
- [ ] v2: downsampling de datos antiguos (raw 7d → 1m hasta 30d → 5m más allá)
- [ ] v2: alertas (ej. notificar si RAM > X durante Y minutos)

## Log

- 2026-05-22 — proyecto creado, esqueleto inicial; v1.0.0 publicado al store
- 2026-05-22 — v1.0.1: fix puerto host 3000→3737 (3000 reservado por umbrelOS, install fallaba al bind del app_proxy). Sólo cambio en manifest; no rebuild.
