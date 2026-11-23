# ctxbomb

**Honeypot pasivo que sirve *context bombs* a atacantes basados en IA, en dos modos: servidor independiente o
integrado en nginx.** · *A passive honeypot that serves context bombs to AI-driven attackers, as a standalone
server or an nginx integration.*

Un agente ofensivo (LLM con herramientas) que encuentra un "secreto" y lo lee mete ese texto en su contexto. Una
*context bomb* es un texto que activa los filtros de seguridad del modelo y corta la sesión. `ctxbomb` coloca esos
textos dentro de recursos señuelo (`/.env`, un secreto tipo AWS, notas de traspaso…), **alerta en cada acceso** y
nunca ataca de vuelta. Sin dependencias: Python 3.9+ (biblioteca estándar) y, para el modo nginx, nginx.

## Dos modos

| | Independiente | nginx |
|---|---|---|
| Qué es | servidor HTTP propio (`python -m ctxbomb serve`) | archivos estáticos + 2 snippets de configuración |
| Para qué | honeypot dedicado, host aislado | añadirlo a un sitio **ya en producción** |
| Proceso extra | sí | no (lo sirve nginx) |
| Selección | `random`, `rotate`, `per_pattern`, `fixed` | `random`, `per_pattern`, `fixed` (reparto por `split_clients`) |
| Alertas | JSONL + webhook | log JSON de nginx (`ctxbomb.log`) |
| Manual | [`docs/MANUAL-standalone.md`](docs/MANUAL-standalone.md) | [`docs/MANUAL-nginx.md`](docs/MANUAL-nginx.md) |

## Inicio rápido

```bash
# independiente
cp config/standalone.example.json config/config.json
python3 -m ctxbomb check -c config/config.json
python3 -m ctxbomb serve -c config/config.json

# nginx (genera los archivos; luego sigue docs/MANUAL-nginx.md)
python3 -m ctxbomb nginx -c config/nginx.example.json -o out/
```

Los textos están en [`payloads/`](payloads/) (un solo directorio). Evidencia medida: [`docs/RESULTADOS.md`](docs/RESULTADOS.md).

## Pruebas

```bash
python3 -m unittest discover -s tests -p "test_*.py"          # unitarias (payloads ficticios)
python3 -m unittest discover -s tests/integration              # nginx real en contenedor (requiere docker + nginx:alpine)
```

La prueba de integración levanta nginx en un contenedor con un sitio simulado, incluye el honeypot con una línea y
verifica: `nginx -t`, que el sitio no cambia, bytes exactos por ruta, cabeceras, reparto de variantes, métodos y
log JSON sin texto de payloads (compara solo hashes).

## Advertencias

- Úsalo **solo en infraestructura propia** y con autorización. Es pasivo, pero sirve contenido pensado para activar filtros de seguridad.
- **Fuego amigo:** cualquier agente tuyo (asistente, triage, resumen de logs) que lea una ruta señuelo puede bloquearse.
  Por eso los logs guardan nombre y hash, nunca el texto.
- **Falsos positivos:** crawlers y escáneres legítimos pueden tocar rutas como `/.env`. Trata el log como señal de
  alta probabilidad, no como prueba de ataque con IA.
- La eficacia depende del modelo y del proveedor y **no está garantizada**; ver los límites en `docs/RESULTADOS.md`.

## Autor

**Marco Torres Y.** (Plaxius) · [Exis](https://exis.cl) · [Axis Dynamics](https://axisdynamics.cl) · mtorres@exis.cl

## Créditos

El concepto de *context bomb* (usar el contenido de recursos señuelo para activar los guardrails de un agente
atacante) fue presentado por **Tracebit Research** — <https://agentic.tracebit.com/context-bombs>. Los textos de
este repositorio son originales; la idea y parte de su estructura se inspiran en ese trabajo.
También inspirado en [`rbidou/aitarpit`](https://github.com/rbidou/aitarpit) (MIT, Renaud Bidou). Proyecto
independiente, sin afiliación con ninguno de los dos. Licencia: MIT.

Nota sobre los textos de Tracebit: su repositorio los publica "for everyone's use" pero no declara ninguna licencia
(revisado en nov-2026), así que este proyecto no los incluye, no los descarga y no depende de ellos.
