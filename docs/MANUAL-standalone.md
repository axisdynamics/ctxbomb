# Manual — honeypot independiente

Un servidor HTTP propio, pasivo (solo GET/HEAD; el resto recibe 405 y se registra). Pensado para un host aislado.

## 1. Instalar y arrancar

    cp config/standalone.example.json config/config.json
    python3 -m ctxbomb check -c config/config.json     # valida rutas y patrones
    python3 -m ctxbomb list  -c config/config.json     # nombres, tamaños y hashes (nunca el contenido)
    python3 -m ctxbomb serve -c config/config.json

Ejecuta los comandos desde la raíz del repositorio (o instala con `pip install .` y usa `ctxbomb ...`).

Docker:

    docker build -f docker/standalone.Dockerfile -t ctxbomb .
    docker run -p 8080:8080 -v $PWD/config/config.json:/app/config/config.json ctxbomb
    # dentro del contenedor usa "host": "0.0.0.0"

## 2. Configuración

| clave | descripción |
|---|---|
| `listen` | `{"host": "127.0.0.1", "port": 8080}` (por defecto solo local) |
| `payloads_dir` | carpeta con los `.txt` (relativa al config) |
| `log_file` | JSONL de alertas |
| `webhook_url` | POST JSON por cada alerta `high` (única llamada saliente); `null` para desactivar |
| `trust_proxy` | `true` si va tras un proxy: usa `X-Forwarded-For` |
| `response_delay_ms` | retardo artificial opcional |
| `bait_index` | `/robots.txt` y `/llms.txt` listan las rutas señuelo |
| `index_links` | `/` enlaza a las rutas señuelo |

### Rutas

    {"path": "/.env", "template": "env", "payloads": ["zh-*"], "select": "random"}

| campo | valores |
|---|---|
| `path` | empieza por `/` |
| `template` | `raw` (solo el texto) · `env` · `json_secret` (secreto tipo AWS) · `text_note` |
| `payloads` | lista de patrones glob sobre el nombre de archivo, p. ej. `["zh-*", "conv-*"]` |
| `select` | `random` · `rotate` (cíclico) · `per_pattern` (uno por cada patrón, juntos) · `fixed` (+ `"file": "nombre"`) |

### Qué patrón usar

| atacante probable | patrón |
|---|---|
| modelo chino por API de proveedor chino | `zh-*` |
| modelo occidental con safeguards | `bio-*` |
| modelo local sin guardrails | `conv-*` |
| no sabes | `per_pattern` con los tres en la misma ruta |

Con `per_pattern` el atacante recibe los tres textos a la vez; solo el que corresponde a su modelo debería surtir efecto.

## 3. Alertas

Cada acceso a una ruta señuelo es `level: "high"`; el resto, `info`:

    {"ts":"…","src_ip":"203.0.113.7","ua":"curl/8.5.0","path":"/.env","level":"high","template":"env",
     "payloads":[{"file":"zh-log-8964.txt","sha256":"…","bytes":108}]}

El log **no contiene el texto**. Ninguna página enlaza a las rutas salvo `robots.txt`/`llms.txt`/`/`.

## 4. Despliegue recomendado

- Host aislado, sin credenciales reales, detrás de un proxy inverso si es público.
- No enlaces las rutas desde páginas de usuarios reales.
- Revisa el log con una herramienta que **no** reenvíe a un LLM el contenido servido.
