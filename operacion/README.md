# Operación y flujos: modelo operacional de Zumaya

Este modelo cubre la producción del ciclotrón y la radiofarmacia, la distribución regional de F-18 FDG,
el flujo de pacientes por área (simulación de eventos discretos con SimPy) y la comparación de las
cargas de trabajo con los supuestos del blindaje. Todos los parámetros están en
`escenarios.yaml`, cada uno con su origen ([IBA], [BD], [LIT] o [SUP]).

> Es un modelo de planeación. Los valores marcados [SUP] son supuestos: hay que confirmarlos
> con IBA, con la operación real y con el registro sanitario antes de usarlos para decidir.

## Cómo ejecutarlo

```bash
pip install --break-system-packages simpy pyyaml numpy matplotlib pandas pytest
cd operacion
python modelo.py                 # 60 réplicas por escenario (~5 s); salidas en resultados/
python modelo.py --replicas 20   # más rápido
python -m pytest -q              # 13 pruebas de decaimiento, producción y entrega
```

## Resultados (`resultados/`)

| Archivo | Contenido |
|---|---|
| `gantt_produccion_E*.png` | Programa diario: arranque, haz, síntesis, QC, inyecciones locales, rutas y Ga-68 |
| `curvas_disponibilidad_E*.png` | F-18 en la radiofarmacia (con decaimiento y retiros), Ga-68 por elución y Cu-64 por lote |
| `mapa_factibilidad_distribucion.png` | Mapa de destinos y matriz de dosis entregables por escenario y corrida |
| `utilizacion_por_area.png` | Utilización de cada equipo y sala; más de 100 % significa tiempo extra |
| `produccion_corridas.csv` | Por corrida: inicio del haz, EOB, EOS, liberación, µA, min, µA·h, GBq y destinos |
| `factibilidad_distribucion.csv` | Para cada ciudad y corrida: llegada, dosis entregables, A(EOS) requerida y motivo |
| `corrida_dedicada_por_ciudad.csv` | Corrida exclusiva para una ciudad: liberación más tardía posible y hora de arranque |
| `sensibilidad_inicio_operacion.csv` | Hora de arranque en los casos optimista, nominal y pesimista, y a 2 × 150 µA |
| `utilizacion.csv`, `esperas_y_tiempo_extra.csv` | Resultados de la simulación (media de las réplicas) |
| `minimos_recursos.csv` | Mínimo de salas de captación, vestidores, asientos, gammacámaras y cuartos de I-131 |
| `personal.csv` | Plantilla de referencia por área (razones OIEA, orientativas) |
| `cargas_vs_diseno_blindaje.csv` | Cargas semanales frente al diseño del blindaje; marca lo que lo excede |
| `resumen.json` | Resumen por escenario |

## Supuestos principales

### Producción de F-18 FDG

- **Rendimiento.** Se calibró con la 4.ª propuesta de IBA: "24 Ci de F-18 en 2 h con 180 µA".
  Con A = I·Ysat·(1 − e^(−λt)), resulta Ysat = 9.29 GBq/µA, es decir, 3.5 GBq/µA·h de rendimiento
  inicial. El dato concuerda con el blanco Nirta HCFT F18-700: 700 GBq en 2 h requieren 142 µA por
  blanco. El valor teórico de blanco grueso a 18 MeV (5–6 GBq/µA·h, Ysat ≈ 14.5 GBq/µA) es más
  optimista. Queda en el YAML como sensibilidad; el modelo usa el de IBA.
- **Haz.** Doble haz con 2 blancos de F-18. Para cada corrida se elige la corriente más baja por
  blanco (40 a 150 µA) que cumple la demanda con t_irr ≤ 120 min, lo que cuida la vida del blanco.
  La irradiación mínima es de 20 min, el arranque de 45 min y la transferencia de 5 min.
- **Síntesis y control de calidad.** Síntesis de 30 min (rango 25–35). RCY de 65 % corregido por
  decaimiento (rango 60–70). QC de 50 min (rango 45–60) con liberación paramétrica. Hay un solo
  módulo Synthera+ (propuesta IBA), con 60 min de limpieza entre síntesis.
- **Dispensación.** Margen de 1.10 por residuos y tolerancia. Caducidad de 10 h después del EOS.
  Límite por bulto tipo A: A2(F-18) = 0.6 TBq.
- **Pacientes locales.** La primera inyección es a las 07:30 y la primera liberación a las 07:00.
  Las dosis locales son de 370 MBq. Las citas siguen la cadencia del tomógrafo (25 min); el 15 %
  de los pacientes PET recibe Ga-68.
- **Distribución.**
  - Las distancias por carretera desde Villahermosa son aproximadas [SUP] y hay que verificarlas:
    Coatzacoalcos 170 km, Cd. del Carmen 175, Tuxtla 290, Campeche 375, Veracruz 470, Mérida 555,
    Oaxaca 700.
  - Velocidad media de 80 km/h, más 15 min de descanso cada 4 h.
  - Embalaje de 20 min, recepción de 30 min y una dosis de 370 MBq cada 20 min en el destino, con
    ventana de inyección de 08:00 a 15:00.
  - La actividad al EOS es A = margen·Σ 370·e^(λ(t_i − EOS)).
  - La demanda regional base (dosis/día) se escala con un factor por escenario: 0.5, 1.0 y 1.5.

### Ga-68 y Cu-64

- **Ga-68.** Generador de 1.85 GBq con 90 días de uso y 70 % de eficiencia de elución. Las
  eluciones se programan según las citas de Ga-68. Se calcula también la alternativa de blanco
  líquido de Zn-68: el supuesto de 0.3 GBq/µA·h da unos 9 GBq al EOB con 40 µA durante 60 min.
- **Cu-64.** Requiere el blanco sólido, que es una opción del KIUBE no incluida en la propuesta
  actual. Se supone 0.2 GBq/µA·h con 30 µA durante 4 h, un lote semanal y unos 14 GBq a la
  liberación.

### Flujo de pacientes (SimPy, 60 réplicas)

- **PET.**
  - Llegada 30 ± 10 min antes de la cita, seguida de entrevista y glucemia (10 min).
  - El paciente pasa por el vestidor y después ocupa la sala de captación, donde se inyecta.
  - Captación de 60 min y micción; la sala se libera cuando el paciente entra al tomógrafo.
  - Estudio de 20–25 min, recuperación de 15 min y vestidor.
  - Se cuenta un acompañante por paciente.
- **Linac.**
  - Citas de 15 min para IMRT/VMAT y de 30 min para la primera fracción (CBCT).
  - En promedio 20 fracciones por curso.
  - QA diaria de 30 min, más la semanal y la mensual (TG-142) prorrateadas, y 45 min de QA de
    plan por paciente nuevo fuera del horario clínico.
  - 3 % de inasistencias y 4 % de probabilidad diaria de falla (30–90 min).
- **TC simulador.** Lo comparten las simulaciones del linac y las imágenes de HDR; HDR tiene
  prioridad.
- **Gamma Knife.**
  - Flujo con marco: marco 15–25 min, RM 30–45, planeación 45–90 (2 estaciones) y tratamiento
    60–120.
  - Variante sin marco: máscara con la planeación hecha el día previo.
- **HDR (Co-60 Flexitron).** Aplicador 30–45 min, TC 15–20, planeación 30–45, tratamiento 15–30 y
  recuperación 45–75 (2 camas).
- **Gammacámara.**
  - Mezcla de protocolos: óseo 40 % (3 h de espera), perfusión de un día 20 %, renal 10 %,
    tiroides 15 % y otros 15 %.
  - La agenda asigna los huecos de cámara a los protocolos cortos y deja la media mañana a los
    óseos.
- **I-131.** Estancia de 2–3 noches más 1 día de descontaminación del cuarto, durante 52 semanas.
- **Criterios de mínimos.**
  - Salas de captación: el retraso de inyección p95 es de 10 min o menos y la jornada no se
    alarga más de 10 min.
  - Vestidores: la espera p95 es de 5 min o menos.
  - Gammacámaras: el tiempo extra p95 es de 30 min o menos.
- **Personal.** Son razones orientativas de IAEA HHR 13 (2015), del Nuclear Medicine Resources
  Manual (2020) y de IAEA RRS 3 (2012, producción de FDG). La plantilla de cada escenario se
  calcula con los mínimos de equipo que eliminan sus cuellos de botella.

### Cargas frente al blindaje

- **Linac.** W primaria = fx/día × 2 Gy × 5 d. La carga de fuga es W_L = W·[(1 − f) + f·C],
  con C_IMRT = 3 y f = 1. Ambas se comparan con los 900 Gy/semana del diseño (30 pac × 2 turnos ×
  5 d × 3 Gy; F87/F88).
- **PET.** Se usa AAPM TG-108 con Γ = 0.092 µSv·m²/(MBq·h) (paciente atenuado) y factor de
  vaciado de 0.85. El diseño supone 60 pac/semana con 740 MBq, 4 salas de captación y un
  tomógrafo.
- **I-131.** El diseño supone 2 pac/semana con 7.4 GBq y 3 días de estancia.
- **Otras áreas.** HDR: 50 pac/semana. GK: 20 pac/semana. Gammacámara: 43 pac/semana. TC
  simulador: 125 estudios/semana. Ciclotrón: 12 000 µA·h/semana y 300 µA.

## Hallazgos (ejecución con 60 réplicas)

| | E1 inicial | E2 medio | E3 máximo |
|---|---|---|---|
| Inicio de operación del ciclotrón (corriente mínima) | 04:12 | 03:43 | 02:53 |
| Inicio a 2 × 150 µA | 04:30 | 04:30 | 04:26 |
| Arranque en el caso pesimista (2 × 150 µA) | 04:15 | 04:15 | 04:06 |
| Carga del ciclotrón (µA·h/semana) | 385 | 700 | 1 163 (10 % del presupuesto) |
| Ciudades con todas sus dosis | Coatzacoalcos, Carmen, Tuxtla, Campeche, Veracruz | Coatzacoalcos, Carmen, Tuxtla, Campeche | Coatzacoalcos, Carmen, Campeche |
| Ciudades con entrega parcial | — | Veracruz 4/8 | Tuxtla 11/12, Veracruz 4/12 |
| Salas de captación mínimas (diseño: 4) | 3 | 3 | **6** |
| Gammacámaras mínimas | 2 (1 al 92 %) | 2 | 4 |
| Cuartos de I-131 en el pico (diseño: 2) | 1 | 2 | **3** |

### Distribución

- **Mérida y Oaxaca no son factibles con las corridas regulares.** Mérida exige una corrida
  dedicada que arranque hacia las 21:30 del día anterior, y aun así solo caben 4 dosis antes de la
  caducidad. Oaxaca no es factible por caducidad ni siquiera con corrida dedicada.
- **Veracruz recibe solo entregas parciales**, porque llega a las 13:28 y la ventana cierra a las
  15:00.

### Cuellos de botella (utilización mayor de 85 % o tiempo extra)

- **Gammacámara.** En E1 trabaja al 92 % y en E3 la demanda equivale a 2.1 cámaras.
- **Linac.** En E2, 45 fracciones en un turno dejan unas 4 h de tiempo extra: hacen falta un
  segundo turno o un segundo linac. En E1 y E3 trabaja al límite si se incluye la QA de planes.
- **PET.** En E2, un solo tomógrafo termina a las 17:15. En E3, las 4 salas de captación generan
  esperas de unos 78 min.
- **Gamma Knife.** En E3, 8 pacientes al día con marco terminan a las 21:34, y a las 19:42 con
  máscara: el equipo mismo es el límite.

### Excesos sobre el diseño del blindaje

- **Linac.** La carga de fuga con IMRT ×3 alcanza 1.5× en E2 y 2.0× en E3, lo que equivale a
  +6 y +10 cm de hormigón en las barreras secundarias si el diseño no consideró el factor IMRT. La
  carga primaria nunca excede el diseño.
- **PET.**
  - Con 555 MBq, la actividad semanal supera el diseño en E2 (1.25×) y en E3 (1.9×).
  - En E3 hacen falta 2 salas de captación más y un segundo tomógrafo que no tienen diseño de
    blindaje.
- **I-131.** En E3 la carga es 1.5× la del diseño.
- **Gamma Knife.** La carga supera el diseño en E2 (1.25×) y en E3 (2×).
- **Gammacámara.** La carga supera el diseño en todos los escenarios: 1.7×, 2.9× y 4.1×.
- **Ciclotrón, HDR y TC simulador** quedan dentro del diseño.
