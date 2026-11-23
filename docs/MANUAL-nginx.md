# Manual — integración con nginx (sitio en producción)

Sin proceso extra: `ctxbomb` **genera** archivos estáticos y dos snippets; nginx los sirve. Tu sitio solo cambia en
**una línea** (`include`) más un archivo copiado a `conf.d/`. Probado con nginx real en contenedor
(`tests/integration/test_nginx_docker.py`).

## 1. Generar

    python3 -m ctxbomb nginx -c config/nginx.example.json -o out/

El config usa las mismas rutas que el modo independiente, más:

    "nginx": {"web_root": "/etc/ctxbomb/www", "log_file": "/var/log/nginx/ctxbomb.log", "noindex": true}

`web_root` y `log_file` son rutas **en el servidor nginx**. Modos de `select` admitidos: `random`, `per_pattern`, `fixed`
(`rotate` necesita estado y no existe en estático). `per_pattern` pre-genera todas las combinaciones (máx. 64).

Salida en `out/`:

| archivo | para qué |
|---|---|
| `www/` | recursos ya renderizados, uno por variante |
| `ctxbomb-http.conf` | contexto `http`: formato de log JSON y `split_clients` (reparto entre variantes) |
| `ctxbomb-server.conf` | un `location = /ruta { … }` por señuelo, para el bloque `server` |
| `robots-snippet.txt` | líneas `Disallow` para añadir a tu `robots.txt` |
| `variants.json` | qué payloads (nombre y hash) tiene cada variante, para atribuir las alertas |

## 2. Instalar en el servidor

    sudo mkdir -p /etc/ctxbomb /etc/nginx/ctxbomb
    sudo cp -r out/www                  /etc/ctxbomb/www
    sudo cp out/ctxbomb-http.conf       /etc/nginx/conf.d/00-ctxbomb-http.conf    # contexto http
    sudo cp out/ctxbomb-server.conf     /etc/nginx/ctxbomb/ctxbomb-server.conf

En el `server { … }` de tu sitio añade **una línea**:

    include /etc/nginx/ctxbomb/ctxbomb-server.conf;

Luego `sudo nginx -t && sudo systemctl reload nginx`, y añade `robots-snippet.txt` a tu `robots.txt`.

> `00-ctxbomb-http.conf` debe cargarse antes que el sitio (el prefijo `00-` lo garantiza si usas `conf.d/*.conf`),
> porque define el `log_format`. Si tu nginx no incluye `conf.d/`, pega su contenido dentro de `http { }`.

## 3. Qué hace cada `location`

- `location = /ruta` (coincidencia exacta: tiene prioridad sobre tus rutas) sirve el archivo de la variante elegida al azar por petición.
- `limit_except GET HEAD { deny all; }`: cualquier otro método recibe 403.
- Cabeceras `Cache-Control: no-store` y `X-Robots-Tag: noindex, nofollow`; sin ETag.
- `access_log` propio: el tráfico señuelo va **solo** a `ctxbomb.log`; el resto de tu sitio no cambia.

## 4. Alertas

`ctxbomb.log` es JSON, una línea por acceso, siempre `level: "high"`:

    {"ts":"…","src_ip":"172.26.0.1","xff":"","host":"…","method":"GET","path":"/.env","ua":"curl/8.5.0",
     "status":200,"bytes":143,"variant":"r0:v00","level":"high"}

`variant` (`r<ruta>:v<n>`) se resuelve en `variants.json`. Envía el log a tu SIEM, o a fail2ban / un `tail -F` con webhook.
Si nginx va detrás de un balanceador o CDN, configura `real_ip_header` / `set_real_ip_from` para que `src_ip` sea el cliente real
(el log guarda también `X-Forwarded-For`).

## 5. Precauciones en producción

- **Colisiones:** elige rutas que tu sitio no use (`/.env`, `/internal/…`). Un `location =` exacto las taparía.
- **Falsos positivos:** escáneres y crawlers legítimos piden `/.env`. Es una señal de alta probabilidad, no una prueba.
- **Fuego amigo:** monitorización o agentes internos que visiten esas rutas pueden bloquearse; excluye sus IPs del `location` si hace falta.
- **Cambiar variantes:** edita `payloads/` o el config, vuelve a generar y copia `out/` (hace falta `reload`).

## 6. Probarlo en un contenedor

    python3 -m ctxbomb nginx -c config/nginx.example.json -o docker/nginx-demo/out
    mkdir -p docker/nginx-demo/logs && chmod 777 docker/nginx-demo/logs
    docker compose -f docker/nginx-demo/docker-compose.yml up -d
    curl -i http://127.0.0.1:8088/            # sitio normal
    curl -i http://127.0.0.1:8088/.env        # señuelo (contenido servido; evita pasarlo a un LLM)
    cat docker/nginx-demo/logs/ctxbomb.log
    docker compose -f docker/nginx-demo/docker-compose.yml down

Prueba automatizada: `python3 -m unittest discover -s tests/integration`.
