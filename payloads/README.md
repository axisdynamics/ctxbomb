# payloads/

Un único directorio plano con todos los textos (`*.txt`). El prefijo del nombre es solo una etiqueta de uso;
las rutas eligen payloads con patrones glob (`"payloads": ["zh-*", "conv-*"]`).

| prefijo | qué es | contra qué actúa |
|---|---|---|
| `zh-*` | términos políticamente sensibles (Tiananmen, `8964`, otros) en envoltorios de log, aviso, prosa, lista | filtros de proveedores de IA chinos servidos por API |
| `conv-*` | conversación falsa (ChatML / Llama) que simula que el operador ordena detenerse | modelos locales sin guardrails |
| `bio-*` | texto diseñado para activar los filtros de seguridad biológica | modelos occidentales con safeguards |

Reglas para añadir los tuyos: texto corto, un archivo por variante, UTF-8, extensión `.txt`. Los `bio-*` deben
mantenerse sin ningún detalle operativo; revísalos antes de publicar.
Evidencia medida de cada familia: `docs/RESULTADOS.md`.
