# Fases de RadioPharma OS sobre el edificio Zumaya

F81 (plantas BIND), F82 (blindajes Zumaya) y F83 (blindaje del ciclotrón Zumaya), trasladadas desde RadioPharma OS el 2026-11-01.

- F82 y F83 leen los PDF versionados en `fuentes/blindaje_GAMMA/`.
- F81 necesita la extracción DXF de su evidencia (`RPOS_AGENTS_ROOT`).

```bash
python -m pytest rpos_fases_zumaya   # 8 pasan, 4 omitidas sin evidencia F81
```
