# Zumaya-AI — Centro Internacional de Neuro-Oncología Zumaya (Villahermosa, Tabasco)

Repositorio del proyecto de instalación: blindajes (ciclotrón, linac, Gamma Knife, braquiterapia, PET-CT, medicina nuclear, CT simulador), análisis de planos, Monte Carlo del búnker, análisis estructural preliminar, geotecnia, informes y documentos fuente. Es común a las plataformas (GAMMA AI, radiopharma-os, Cyclotron-SIM, RadShieldMx).

> **Privado, uso interno.** Los documentos son propiedad del usuario, que tiene los derechos de uso.

## Estructura

| Carpeta | Contenido |
|---|---|
| `fuentes/planos` | DWG BIND 28-10-26 y planta baja 31-10-26 (con contraventeos) |
| `fuentes/blindaje_GAMMA` | Estimaciones de blindaje de GAMMA Consultoría (oncología y ciclotrón) |
| `fuentes/tabiques` | Fichas CONTUPLEX TD-250/350/400/500/550 e informes IMCYC OT-521 |
| `fuentes/geotecnia` | Estudio de mecánica de suelos OD Ingeniería (2025) |
| `fuentes/ciclotron_IBA` | Propuesta IBA y Site Requirement Guide del KIUBE |
| `blindaje/datos` | `bd_blindaje_zumaya.json`: BD con md5 de cada fuente |
| `blindaje/pipelines` | Fases F86–F89 (Python) y pruebas |
| `blindaje/evidencia` | Salidas JSON por fase |
| `analisis_plano` | Extracción DWG→DXF (LibreDWG 0.13 + ezdxf), figuras |
| `mc_ciclotron` | Resultados MC del búnker (F89; F90 validado contra IBA en Cyclotron-SIM) |
| `informes` | PDF del informe de blindajes, Excel del linac TD-550 |
| `rpos_fases` | Parches originales F86–F89 (radiopharma-os) |

## Estado (31/10/2026)

- **Ciclotrón.** F90 doble haz sin puertas blindadas, validado contra la SRG de IBA: el muro este necesita ≈ 2.08 m de tabique 2.5. Las demás caras siguen en cálculo. Pendientes: composición del TD-250 (análisis químico en proceso) y documentos IBA.
- **Linac Versa HD 15 MV.** Muros cortos aun con TD-550 = 5.5. Pendiente el pesaje de piezas.
- **Estructura.** Búnkeres sobre pilas (qa superficial de 4.9–5.5 t/m²). El linac no tiene junta constructiva.
- **Pendientes de otras áreas.** Puerta HDR Co-60, puerta y laberinto del linac, layout de radiofarmacia, puertas PET.

## Ejecutar

```bash
cd blindaje/pipelines
RPOS_EVIDENCIA=../evidencia KIUBE_RAIZ=<ruta a Cyclotron-SIM/machines/iba_kiube> python -m pytest -q
```
