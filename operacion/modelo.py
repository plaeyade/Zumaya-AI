"""Modelo operacional del Centro Internacional de Neuro-Oncología Zumaya (Villahermosa, Tabasco).

Tres bloques, todos parametrizados en ``escenarios.yaml``:

1. Producción del ciclotrón IBA KIUBE y la radiofarmacia (F-18 FDG, Ga-68, Cu-64): plan diario
   hacia atrás desde la hora de liberación, actividad requerida al fin de síntesis (EOS) para
   entregar N dosis en cada destino, factibilidad de distribución regional por carretera,
   diagrama de Gantt y curvas de disponibilidad corregidas por decaimiento.
2. Simulación de eventos discretos (SimPy) del flujo de pacientes por área (PET/CT, acelerador
   lineal, Gamma Knife, HDR, gammacámara, terapia con I-131) para los tres escenarios:
   utilización, esperas, cuellos de botella, mínimos de salas/vestidores/asientos y personal.
3. Consistencia con el blindaje: cargas semanales implicadas frente a los supuestos de diseño
   (linac W = 900 Gy/semana, PET TG-108, cuartos de I-131, etc.).

Uso:
    python operacion/modelo.py                 # todos los escenarios, salidas en operacion/resultados
    python operacion/modelo.py --replicas 20   # menos réplicas (más rápido)

Tiempo interno: minutos desde la medianoche del día de operación (negativo = día anterior).
"""
from __future__ import annotations

import argparse
import json
import math
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

AQUI = Path(__file__).resolve().parent
LN2 = math.log(2.0)

# --------------------------------------------------------------------------------------------
# Utilidades de tiempo
# --------------------------------------------------------------------------------------------


def a_min(hhmm: str) -> float:
    """'07:30' -> 450.0 minutos desde la medianoche."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def a_hhmm(t: float) -> str:
    """Minutos -> 'HH:MM'; antes de la medianoche se marca como '(-1d) HH:MM'."""
    t = round(t)
    pref = ""
    if t < 0:
        pref, t = "(-1d) ", t + 1440
    elif t >= 1440:
        pref, t = "(+1d) ", t - 1440
    return f"{pref}{int(t // 60):02d}:{int(t % 60):02d}"


# --------------------------------------------------------------------------------------------
# 1. Física: decaimiento, producción y distribución
# --------------------------------------------------------------------------------------------


def constante_decaimiento(t12_min: float) -> float:
    """lambda en 1/min."""
    return LN2 / t12_min


def decaer(A: float, dt_min: float, t12_min: float) -> float:
    """Actividad tras dt minutos (dt negativo = actividad previa necesaria)."""
    return A * math.exp(-constante_decaimiento(t12_min) * dt_min)


def actividad_requerida(dosis_MBq: float, tiempos_uso: list[float], t_ref: float, t12_min: float,
                        margen: float = 1.0) -> float:
    """Actividad (MBq) a la hora t_ref para disponer de ``dosis_MBq`` en cada tiempo de uso.

    A(t_ref) = margen x sum_i D e^{lambda (t_i - t_ref)}
    """
    lam = constante_decaimiento(t12_min)
    return margen * sum(dosis_MBq * math.exp(lam * (t - t_ref)) for t in tiempos_uso)


def factor_saturacion(t_irr_min: float, t12_min: float) -> float:
    return 1.0 - math.exp(-constante_decaimiento(t12_min) * t_irr_min)


def actividad_eob(I_uA: float, ysat_GBq_uA: float, t_irr_min: float, t12_min: float) -> float:
    """Actividad al fin del bombardeo (GBq): A = I Ysat (1 - e^{-lambda t})."""
    return I_uA * ysat_GBq_uA * factor_saturacion(t_irr_min, t12_min)


def tiempo_irradiacion(A_GBq: float, I_uA: float, ysat_GBq_uA: float, t12_min: float) -> float | None:
    """Tiempo de irradiación (min) para alcanzar A_GBq al EOB; None si supera la saturación."""
    Asat = I_uA * ysat_GBq_uA
    if A_GBq <= 0:
        return 0.0
    if A_GBq >= Asat:
        return None
    return -math.log(1.0 - A_GBq / Asat) / constante_decaimiento(t12_min)


def ysat_desde_rendimiento_inicial(Y_GBq_uAh: float, t12_min: float) -> float:
    """Rendimiento de saturación (GBq/uA) desde el rendimiento inicial (GBq/uAh): Ysat = Y / lambda[h^-1]."""
    return Y_GBq_uAh / (constante_decaimiento(t12_min) * 60.0)


def ysat_desde_dato_fabricante(A_GBq: float, I_uA: float, t_irr_min: float, t12_min: float) -> float:
    """Calibra Ysat con un dato 'A GBq en t min con I uA' (p. ej., IBA: 888 GBq, 180 uA, 120 min)."""
    return A_GBq / (I_uA * factor_saturacion(t_irr_min, t12_min))


def tiempo_traslado(km: float, v_kmh: float, parada_min_cada_4h: float = 0.0) -> float:
    """Minutos de traslado por carretera: distancia / velocidad + paradas de descanso."""
    t = km / v_kmh * 60.0
    return t + parada_min_cada_4h * math.floor(t / 240.0)


def factibilidad_destino(ciudad: dict, n_dosis: int, liberacion: float, P: dict) -> dict:
    """Evalúa si una corrida liberada a la hora ``liberacion`` entrega ``n_dosis`` en ``ciudad``.

    Criterios: (a) primera dosis no antes de la ventana y después de llegada + recepción;
    (b) última dosis dentro de la ventana y antes de la caducidad (EOS + caducidad);
    (c) actividad del bulto a la salida <= límite de bulto tipo A.
    """
    rf, di = P["radiofarmacia"], P["distribucion"]
    t12 = P["fisica"]["t12_min"]["F18"]
    eos = liberacion - rf["qc_FDG_min"]
    salida = liberacion + rf["embalaje_min"]
    transito = tiempo_traslado(ciudad["km"], di["velocidad_kmh"], di["parada_min_cada_4h"])
    llegada = salida + transito
    v0, v1 = a_min(ciudad["ventana"][0]), a_min(ciudad["ventana"][1])
    inicio = max(v0, llegada + di["recepcion_min"])
    fin = min(v1, eos + rf["caducidad_FDG_h"] * 60.0)
    paso = di["intervalo_dosis_min"]
    entregables = 0 if fin < inicio else int((fin - inicio) // paso) + 1
    n = min(n_dosis, entregables)
    tiempos = [inicio + k * paso for k in range(n)]
    A_eos = actividad_requerida(di["dosis_destino_MBq"], tiempos, eos, t12, rf["margen_dispensacion"]) / 1000.0
    A_salida = decaer(A_eos, salida - eos, t12)
    motivo = []
    if entregables == 0:
        motivo.append("llega después de la ventana o de la caducidad")
    elif entregables < n_dosis:
        motivo.append(f"solo {entregables} dosis antes del cierre/caducidad")
    if A_salida > rf["limite_bulto_tipo_A_GBq"]:
        motivo.append("excede bulto tipo A")
    return dict(ciudad=ciudad["nombre"], km=ciudad["km"], transito_h=round(transito / 60, 2),
                liberacion=a_hhmm(liberacion), llegada=a_hhmm(llegada),
                primera_dosis=a_hhmm(inicio) if n else "-", ultima_dosis=a_hhmm(tiempos[-1]) if n else "-",
                dosis_solicitadas=n_dosis, dosis_entregables=n, A_EOS_GBq=round(A_eos, 2),
                A_salida_GBq=round(A_salida, 2),
                factor_decaimiento=round(A_eos * 1000 / max(n, 1) / di["dosis_destino_MBq"], 2) if n else None,
                factible=(n == n_dosis and n > 0 and A_salida <= rf["limite_bulto_tipo_A_GBq"]),
                parcial=(0 < n < n_dosis), motivo="; ".join(motivo) or "ok",
                _tiempos=tiempos, _salida=salida, _llegada=llegada)


def corrida_dedicada(ciudad: dict, n_dosis: int, P: dict) -> dict:
    """Corrida dedicada: liberación más tardía que aún llega al inicio de la ventana.

    Devuelve la hora de inicio de operaciones del ciclotrón que exigiría y cuántas dosis caben
    antes de la caducidad.
    """
    rf, di, cy = P["radiofarmacia"], P["distribucion"], P["ciclotron"]
    transito = tiempo_traslado(ciudad["km"], di["velocidad_kmh"], di["parada_min_cada_4h"])
    lib = a_min(ciudad["ventana"][0]) - di["recepcion_min"] - transito - rf["embalaje_min"]
    r = factibilidad_destino(ciudad, n_dosis, lib, P)
    t12 = P["fisica"]["t12_min"]["F18"]
    eos = lib - rf["qc_FDG_min"]
    A_eob = r["A_EOS_GBq"] / (rf["rcy_FDG_corregido"] * math.exp(-constante_decaimiento(t12) * (rf["sintesis_FDG_min"] + cy["transferencia_min"])))
    I = cy["corriente_max_total_uA"]
    t_irr = tiempo_irradiacion(A_eob, I, cy["ysat_F18_GBq_uA"], t12) or cy["t_irr_max"]
    t_irr = max(t_irr, cy["t_irr_min"])
    inicio = eos - rf["sintesis_FDG_min"] - cy["transferencia_min"] - t_irr - cy["arranque_min"]
    r.update(dict(liberacion_dedicada=a_hhmm(lib), inicio_operacion_dedicada=a_hhmm(inicio),
                  t_irr_min_a_300uA=round(t_irr, 1)))
    return r


# ---------------------------------------------------------------- plan diario de producción FDG


@dataclass
class Corrida:
    nombre: str
    liberacion: float
    demanda_local: list = field(default_factory=list)      # tiempos de inyección local
    destinos: list = field(default_factory=list)           # resultados de factibilidad asignados
    I_blanco: float = 0.0
    t_irr: float = 0.0
    A_EOB: float = 0.0
    A_EOS: float = 0.0
    A_EOS_req: float = 0.0
    alerta: str = ""

    def tiempos(self, P):
        rf, cy = P["radiofarmacia"], P["ciclotron"]
        eos = self.liberacion - rf["qc_FDG_min"]
        ini_sint = eos - rf["sintesis_FDG_min"]
        eob = ini_sint - cy["transferencia_min"]
        sob = eob - self.t_irr
        return dict(SOB=sob, EOB=eob, ini_sintesis=ini_sint, EOS=eos, liberacion=self.liberacion)


def programa_pet(n: int, escaneres: int, D: dict) -> list[dict]:
    """Agenda determinista PET: escáner s, posición k; escalonado entre escáneres."""
    t0 = a_min(D["inicio_inyecciones"])
    slot = D["cadencia_slot_min"]
    out = []
    for i in range(n):
        s, k = i % escaneres, i // escaneres
        t_iny = t0 + k * slot + s * slot / escaneres
        out.append(dict(id=i, escaner=s, t_iny=t_iny,
                        t_scan=t_iny + D["inyeccion_min"] + D["captacion_min"] + D["miccion_min"]))
    return out


def separar_radiofarmacos(prog: list[dict], frac_ga: float) -> tuple[list[float], list[float]]:
    """Reparte las inyecciones PET entre FDG y Ga-68 (cada ~1/frac pacientes, desde el 3.º)."""
    n = len(prog)
    n_ga = int(round(n * frac_ga))
    idx_ga = set()
    if n_ga:
        paso = n / n_ga
        idx_ga = {min(n - 1, int(2 + k * paso)) for k in range(n_ga)}
    fdg = [p["t_iny"] for p in prog if p["id"] not in idx_ga]
    ga = [p["t_iny"] for p in prog if p["id"] in idx_ga]
    return fdg, ga


def planificar_produccion(esc: dict, P: dict, rf_override: dict | None = None) -> dict:
    """Plan diario FDG: asignación de destinos y pacientes a corridas, corriente y tiempos.

    Se itera hasta que no haya conflictos de recursos (ciclotrón, módulo de síntesis, QC).
    """
    P = json.loads(json.dumps(P))
    if rf_override:
        P["radiofarmacia"].update(rf_override)
    rf, cy, di = P["radiofarmacia"], P["ciclotron"], P["distribucion"]
    t12 = P["fisica"]["t12_min"]["F18"]
    prog = programa_pet(esc["pet"]["pacientes_dia"], esc["pet"]["escaneres"], P["des"]["pet"])
    t_fdg, t_ga = separar_radiofarmacos(prog, esc["pet"]["fraccion_Ga68"])
    libs = [a_min(x) for x in esc["produccion"]["liberaciones"]]
    # la primera liberación debe abastecer la primera inyección local
    libs[0] = min(libs[0], min(t_fdg) - rf["dispensacion_min"] - 20)
    factor = esc["produccion"]["factor_regional"]
    pedidos = {c["nombre"]: max(1, int(round(c["dosis_base"] * factor))) for c in di["ciudades"]}

    for _ in range(8):
        corridas = [Corrida(f"Corrida {i + 1}", L) for i, L in enumerate(libs)]
        # destinos: la corrida factible con menor actividad; si ninguna, la parcial con más dosis
        tabla = []
        for c in di["ciudades"]:
            evals = [factibilidad_destino(c, pedidos[c["nombre"]], cr.liberacion, P) for cr in corridas]
            for k, e in enumerate(evals):
                tabla.append(dict(corrida=corridas[k].nombre, **{q: v for q, v in e.items() if not q.startswith("_")}))
            ok = [(e["A_EOS_GBq"], k) for k, e in enumerate(evals) if e["factible"]]
            if ok:
                k = min(ok)[1]
            else:
                parc = [(e["dosis_entregables"], -e["A_EOS_GBq"], k) for k, e in enumerate(evals)
                        if e["dosis_entregables"] > 0 and "tipo A" not in e["motivo"]]
                k = max(parc)[2] if parc else None
            if k is not None:
                corridas[k].destinos.append(evals[k])
        # pacientes locales: corrida más reciente liberada a tiempo
        for t in t_fdg:
            cands = [cr for cr in corridas if cr.liberacion + rf["dispensacion_min"] <= t]
            (cands[-1] if cands else corridas[0]).demanda_local.append(t)
        # corriente y tiempo de irradiación por corrida
        f_sint = rf["rcy_FDG_corregido"] * math.exp(-constante_decaimiento(t12) * (rf["sintesis_FDG_min"] + cy["transferencia_min"]))
        for cr in corridas:
            eos = cr.liberacion - rf["qc_FDG_min"]
            loc = actividad_requerida(esc["pet"]["A0_MBq"], cr.demanda_local, eos, t12, rf["margen_dispensacion"]) / 1000.0
            reg = sum(d["A_EOS_GBq"] for d in cr.destinos)
            cr.A_EOS_req = loc + reg
            A_eob_req = cr.A_EOS_req / f_sint
            nb = cy["blancos_F18"]
            elegido = None
            for I in cy["corrientes_blanco_uA"]:
                t = tiempo_irradiacion(A_eob_req, I * nb, cy["ysat_F18_GBq_uA"], t12)
                if t is not None and t <= cy["t_irr_max"]:
                    elegido = (I, max(t, cy["t_irr_min"]))
                    break
            if elegido is None:
                elegido = (cy["corriente_max_blanco_uA"], cy["t_irr_max"])
                cr.alerta = "demanda > capacidad de 2 h a 2x150 uA"
            cr.I_blanco, cr.t_irr = elegido
            cr.A_EOB = actividad_eob(cr.I_blanco * nb, cy["ysat_F18_GBq_uA"], cr.t_irr, t12)
            cr.A_EOS = cr.A_EOB * f_sint
            if cr.A_EOB / nb > cy["capacidad_blanco_GBq"] * 1.001:
                cr.alerta += " | excede capacidad nominal del blanco"
        # conflictos de recursos: ciclotrón, síntesis (1 módulo), QC
        cambio = False
        for k in range(1, len(corridas)):
            a, b = corridas[k - 1].tiempos(P), corridas[k].tiempos(P)
            retraso = max(
                (a["EOB"] + cy["recarga_blanco_min"]) - b["SOB"],
                (a["EOS"] + rf["limpieza_entre_sintesis_min"]) - b["ini_sintesis"] if rf["modulos_sintesis"] == 1 else -1e9,
                a["liberacion"] - b["EOS"],
            )
            if retraso > 0.5:
                libs[k] += math.ceil(retraso)
                cambio = True
        if not cambio:
            break

    t0 = corridas[0].tiempos(P)
    inicio_op = t0["SOB"] - cy["arranque_min"]
    A_eob1 = corridas[0].A_EOS_req / f_sint
    t300 = tiempo_irradiacion(A_eob1, cy["corriente_max_total_uA"], cy["ysat_F18_GBq_uA"], t12) or cy["t_irr_max"]
    inicio_300 = t0["EOB"] - max(t300, cy["t_irr_min"]) - cy["arranque_min"]
    uah_dia = sum(cr.I_blanco * cy["blancos_F18"] * cr.t_irr / 60.0 for cr in corridas)
    return dict(corridas=corridas, tabla_factibilidad=tabla, A0=esc["pet"]["A0_MBq"], inicio_operacion_300uA=inicio_300, pedidos=pedidos, inicio_operacion=inicio_op,
                t_fdg=t_fdg, t_ga=t_ga, programa_pet=prog, uAh_dia=uah_dia,
                horas_haz_dia=sum(cr.t_irr for cr in corridas) / 60.0, P=P)


def plan_galio68(t_ga: list[float], P: dict) -> dict:
    """Elusiones del generador Ge-68/Ga-68 programadas según las citas de Ga-68.

    Cada elución se libera 10 min antes de la primera cita pendiente y atiende las siguientes
    mientras alcance la actividad; el recrecimiento de Ga-68 se calcula desde la elución previa.
    """
    g, t12 = P["galio68"], P["fisica"]["t12_min"]
    lam = constante_decaimiento(t12["Ga68"])
    A_ge = g["generador_GBq_calibracion"] * math.exp(-LN2 * g["edad_generador_d"] / P["fisica"]["t12_Ge68_d"])
    proc = g["marcaje_min"] + g["qc_min"]
    pend, lotes, previo = sorted(t_ga), [], None
    while pend:
        lib = pend[0] - 10
        te = lib - proc
        crec = 1.0 if previo is None else factor_saturacion(te - previo, t12["Ga68"])
        A_el = A_ge * crec * g["eficiencia_elucion"]
        A_lib = A_el * g["rcy_marcaje"] * math.exp(-lam * proc)
        servidos, resto = [], A_lib * 1000
        for t in pend:
            need = g["dosis_MBq"] * math.exp(lam * (t - lib))
            if need > resto:
                break
            servidos.append(t)
            resto -= need
        lotes.append(dict(elucion=te, liberacion=lib, A_elucion_GBq=A_el, A_liberacion_GBq=A_lib,
                          pacientes=len(servidos), tiempos=servidos, recrecimiento=crec))
        if not servidos:          # ni una dosis: la cita no se puede atender con el generador
            pend = pend[1:]
        else:
            pend = pend[len(servidos):]
        previo = te
    no_atendidos = len(t_ga) - sum(lo["pacientes"] for lo in lotes)
    bl = g["blanco_liquido"]
    ys = ysat_desde_rendimiento_inicial(bl["rendimiento_inicial_GBq_uAh"], t12["Ga68"])
    A_liq = actividad_eob(bl["corriente_uA"], ys, bl["t_irr_min"], t12["Ga68"])
    A_liq_lib = A_liq * bl["rcy"] * math.exp(-lam * bl["purificacion_min"])
    return dict(A_Ge68_GBq=A_ge, lotes=lotes, no_atendidos=no_atendidos,
                blanco_liquido=dict(Ysat_GBq_uA=ys, A_EOB_GBq=A_liq, A_liberacion_GBq=A_liq_lib,
                                    dosis_150MBq_a_1h=int(A_liq_lib * 1000 * math.exp(-lam * 60) // g["dosis_MBq"]),
                                    uAh=bl["corriente_uA"] * bl["t_irr_min"] / 60))


def plan_cobre64(n_sem: int, P: dict) -> dict:
    c, t12 = P["cobre64"], P["fisica"]["t12_min"]["Cu64"]
    ys = ysat_desde_rendimiento_inicial(c["rendimiento_inicial_GBq_uAh"], t12)
    A_eob = actividad_eob(c["corriente_uA"], ys, c["t_irr_min"], t12)
    A_lib = A_eob * c["rcy"] * math.exp(-constante_decaimiento(t12) * (c["procesamiento_min"] + c["qc_min"]))
    # horas tras la liberación en que aún hay >= 1 dosis
    h_util = math.log(A_lib * 1000 / c["dosis_MBq"]) / (constante_decaimiento(t12) * 60) if A_lib * 1000 > c["dosis_MBq"] else 0
    return dict(Ysat_GBq_uA=ys, A_EOB_GBq=A_eob, A_liberacion_GBq=A_lib, dosis_a_liberacion=int(A_lib * 1000 // c["dosis_MBq"]),
                horas_util_1dosis=h_util, uAh_lote=c["corriente_uA"] * c["t_irr_min"] / 60 if n_sem > 0 else 0.0,
                pacientes_semana=n_sem)


# --------------------------------------------------------------------------------------------
# 2. Simulación de eventos discretos (SimPy)
# --------------------------------------------------------------------------------------------


class Ocupacion:
    """Registro de ocupación (asientos, camas) para obtener el pico."""

    def __init__(self, env):
        self.env, self.n, self.pico = env, 0.0, 0.0

    def cambio(self, d):
        self.n += d
        self.pico = max(self.pico, self.n)


def _u(rng, ab):
    return float(rng.uniform(ab[0], ab[1]))


def sim_pet(par: dict, D: dict, rng, n_salas=None, n_vest=None) -> dict:
    import simpy
    env = simpy.Environment()
    n_salas = n_salas or par["salas_captacion"]
    n_vest = n_vest or par["vestidores"]
    salas = simpy.Resource(env, n_salas)
    vest = simpy.Resource(env, n_vest)
    enf = simpy.Resource(env, par["enfermeria"])
    esc = [simpy.Resource(env, 1) for _ in range(par["escaneres"])]
    espera = Ocupacion(env)
    m = dict(espera_sala=[], retraso_iny=[], espera_vest=[], fin=[], ocup_esc=[0.0] * par["escaneres"],
             ocup_salas=0.0, espera_escaner=[])

    def paciente(p):
        lleg = max(0.0, p["t_iny"] - D["llegada_antelacion_min"] + rng.normal(0, D["llegada_sd_min"]))
        yield env.timeout(lleg)
        espera.cambio(1 + D["acompanantes"])
        yield env.timeout(D["entrevista_glucemia_min"])
        t0 = env.now
        with vest.request() as r:
            yield r
            m["espera_vest"].append(env.now - t0)
            yield env.timeout(D["vestidor_min"])
        t0 = env.now
        rs = salas.request()
        yield rs
        t_sala = env.now
        espera.cambio(-1)
        m["espera_sala"].append(env.now - t0)
        if env.now < p["t_iny"]:
            yield env.timeout(p["t_iny"] - env.now)
        with enf.request() as r:
            yield r
            yield env.timeout(D["inyeccion_min"])
        m["retraso_iny"].append(env.now - D["inyeccion_min"] - p["t_iny"])
        yield env.timeout(D["captacion_min"] + D["miccion_min"])
        t0 = env.now
        re = esc[p["escaner"]].request()
        yield re
        m["espera_escaner"].append(env.now - t0)
        salas.release(rs)
        m["ocup_salas"] += env.now - t_sala
        d = _u(rng, D["escaneo_min"])
        yield env.timeout(d)
        m["ocup_esc"][p["escaner"]] += d
        esc[p["escaner"]].release(re)
        yield env.timeout(D["recuperacion_min"])
        with vest.request() as r:
            yield r
            yield env.timeout(D["vestidor_min"])
        espera.cambio(-D["acompanantes"])
        m["fin"].append(env.now)

    for p in programa_pet(par["pacientes_dia"], par["escaneres"], D):
        env.process(paciente(p))
    env.run()
    j0, j1 = a_min(par["jornada"][0]), a_min(par["jornada"][1])
    return dict(util_escaner=sum(m["ocup_esc"]) / (par["escaneres"] * (j1 - j0)),
                util_salas=m["ocup_salas"] / (n_salas * (j1 - j0)),
                espera_sala_media=float(np.mean(m["espera_sala"])), retraso_iny_p95=float(np.percentile(m["retraso_iny"], 95)),
                espera_vest_p95=float(np.percentile(m["espera_vest"], 95)), fin=max(m["fin"]),
                extra_min=max(0.0, max(m["fin"]) - j1), pico_espera=espera.pico,
                espera_escaner_media=float(np.mean(m["espera_escaner"])))


def sim_linac_tc(esc: dict, D: dict, Dh: dict, rng) -> dict:
    """Acelerador (uno o más turnos) + TC simulador compartido con HDR; HDR modelado aquí también."""
    import simpy
    env = simpy.Environment()
    L = esc["linac"]
    lin = simpy.PriorityResource(env, L["unidades"])
    tc = simpy.PriorityResource(env, 1)
    espera = Ocupacion(env)
    j0, j1 = a_min(L["jornada"][0]), a_min(L["jornada"][1])
    n = L["fracciones_dia"]
    nuevos = int(rng.binomial(n, 1.0 / D["fracciones_por_curso"]))
    m = dict(espera=[], ocup=0.0, fin=j0, ocup_tc=0.0, hdr_fin=[], hdr_espera_tc=[], hdr_ocup=0.0,
             hdr_proc=0.0, hdr_ciclo=[])
    # agenda
    agenda, t = [], j0 + D["qa_diaria_min"]
    for i in range(n):
        dur = D["slot_primera_fx_min"] if i < nuevos else D["slot_min"]
        agenda.append((t, dur))
        t += dur / L["unidades"]

    def paciente(t_slot, slot):
        if rng.random() < D["inasistencia"]:
            return
        lleg = max(0.0, t_slot - D["llegada_antelacion_min"] + rng.normal(0, D["llegada_sd_min"]))
        yield env.timeout(lleg)
        comp = 1 if rng.random() < D["acompanantes_p"] else 0
        espera.cambio(1 + comp)
        t0 = env.now
        with lin.request(priority=1) as r:
            yield r
            if env.now < t_slot - 5:           # no se adelanta más de 5 min
                yield env.timeout(t_slot - 5 - env.now)
            espera.cambio(-1 - comp)
            m["espera"].append(env.now - t0)
            mu = D["duracion_relativa"] * slot
            s = math.sqrt(math.log(1 + D["duracion_cv"] ** 2))
            d = float(rng.lognormal(math.log(mu) - s * s / 2, s))
            yield env.timeout(d)
            m["ocup"] += d
            m["fin"] = max(m["fin"], env.now)

    def falla():
        yield env.timeout(_u(rng, (j0 + 60, j1 - 60)))
        with lin.request(priority=0) as r:
            yield r
            yield env.timeout(_u(rng, D["falla_min"]))

    def simulacion_tc(t):
        yield env.timeout(t)
        with tc.request(priority=1) as r:
            yield r
            yield env.timeout(D["simulacion_TC_min"])
            m["ocup_tc"] += D["simulacion_TC_min"]

    # HDR
    H = esc["hdr"]
    proc = simpy.Resource(env, 1)
    plan = simpy.Resource(env, 1)
    hdr = simpy.Resource(env, 1)
    camas = simpy.Resource(env, Dh["camas_recuperacion"])

    def paciente_hdr(t):
        yield env.timeout(t)
        t_ini = env.now
        with proc.request() as r:
            yield r
            d = _u(rng, Dh["aplicador_min"])
            yield env.timeout(d)
            m["hdr_proc"] += d
        t0 = env.now
        with tc.request(priority=0) as r:
            yield r
            m["hdr_espera_tc"].append(env.now - t0)
            d = _u(rng, Dh["imagen_TC_min"])
            yield env.timeout(d)
            m["ocup_tc"] += d
        with plan.request() as r:
            yield r
            yield env.timeout(_u(rng, Dh["planeacion_min"]))
        with hdr.request() as r:
            yield r
            d = _u(rng, Dh["tratamiento_min"])
            yield env.timeout(d)
            m["hdr_ocup"] += d
        with camas.request() as r:
            yield r
            yield env.timeout(_u(rng, Dh["retiro_recuperacion_min"]))
        m["hdr_fin"].append(env.now)
        m["hdr_ciclo"].append(env.now - t_ini)

    for ts, dur in agenda:
        env.process(paciente(ts, dur))
    if rng.random() < D["p_falla_dia"]:
        env.process(falla())
    for k in range(nuevos):
        env.process(simulacion_tc(j0 + 60 + 45 * k))
    h0 = a_min(Dh["primera_llegada"])
    # intervalo de citas: el nominal, comprimido si el último ciclo (~3 h) no cabe en la jornada
    hj1_ = a_min(H["jornada"][1])
    iv = Dh["intervalo_min"] if H["pacientes_dia"] < 2 else min(Dh["intervalo_min"], max(20.0, (hj1_ - 180 - h0) / (H["pacientes_dia"] - 1)))
    for k in range(H["pacientes_dia"]):
        env.process(paciente_hdr(h0 + k * iv))
    env.run()
    disp = L["unidades"] * (j1 - j0)
    qa_prorr = D["qa_diaria_min"] + D["qa_semanal_min"] / 5 + D["qa_mensual_min"] / 20 + nuevos * D["qa_paciente_min"]
    hj0, hj1 = a_min(H["jornada"][0]), a_min(H["jornada"][1])
    return dict(util_linac=m["ocup"] / disp, util_linac_con_QA=(m["ocup"] + qa_prorr * L["unidades"]) / disp,
                espera_linac_media=float(np.mean(m["espera"])), espera_linac_p95=float(np.percentile(m["espera"], 95)),
                extra_linac_min=max(0.0, m["fin"] - j1), pico_espera_linac=espera.pico, nuevos=nuevos,
                util_tc=m["ocup_tc"] / (8 * 60), util_hdr=m["hdr_ocup"] / (hj1 - hj0),
                util_sala_proc_hdr=m["hdr_proc"] / (hj1 - hj0),
                espera_tc_hdr_media=float(np.mean(m["hdr_espera_tc"])) if m["hdr_espera_tc"] else 0.0,
                extra_hdr_min=max(0.0, max(m["hdr_fin"]) - hj1) if m["hdr_fin"] else 0.0,
                ciclo_hdr_h=float(np.mean(m["hdr_ciclo"])) / 60 if m["hdr_ciclo"] else 0.0)


def sim_gk(par: dict, D: dict, rng) -> dict:
    import simpy
    env = simpy.Environment()
    marco = simpy.Resource(env, 1)
    rm = simpy.Resource(env, 1)
    plan = simpy.Resource(env, D["estaciones_planeacion"])
    gk = simpy.Resource(env, 1)
    m = dict(ocup=0.0, fin=[], espera_gk=[], ocup_rm=0.0, ocup_plan=0.0)

    def paciente(i):
        yield env.timeout(a_min(D["llegada"]) + 20 * i)
        if par["flujo"] == "marco":
            with marco.request() as r:
                yield r
                yield env.timeout(_u(rng, D["marco_min"]))
            with rm.request() as r:
                yield r
                d = _u(rng, D["rm_min"])
                yield env.timeout(d)
                m["ocup_rm"] += d
            with plan.request() as r:
                yield r
                d = _u(rng, D["planeacion_min"])
                yield env.timeout(d)
                m["ocup_plan"] += d
        else:                                    # máscara con planeación del día previo
            yield env.timeout(15)
        t0 = env.now
        with gk.request() as r:
            yield r
            m["espera_gk"].append(env.now - t0)
            d = _u(rng, D["tratamiento_min"])
            yield env.timeout(d)
            m["ocup"] += d
        yield env.timeout(D["retiro_min"] + D["recuperacion_min"])
        m["fin"].append(env.now)

    for i in range(par["pacientes_dia"]):
        env.process(paciente(i))
    env.run()
    j0, j1 = a_min(par["jornada"][0]), a_min(par["jornada"][1])
    return dict(util_gk=m["ocup"] / (j1 - j0), fin_gk=max(m["fin"]), extra_gk_min=max(0.0, max(m["fin"]) - j1),
                espera_gk_media=float(np.mean(m["espera_gk"])), util_rm_gk=m["ocup_rm"] / (j1 - j0))


def agenda_gammacamara(prot: list[str], D: dict, camaras: int) -> list[tuple[str, float]]:
    """Agenda por huecos de cámara: en cada hueco libre se cita al paciente con la preparación
    más larga que aún pueda llegar después de la apertura (los óseos llenan la media mañana y los
    protocolos cortos la primera hora)."""
    t_abre = a_min(D["primera_llegada"])
    libre = [t_abre + 15.0] * camaras
    pend = list(prot)
    out = []

    def pre(k):          # minutos antes de la primera sesión de cámara
        t = 0.0
        for tipo, dur in D["protocolos"][k][1]:
            if tipo == "camara":
                break
            t += dur
        return t

    def cam(k):
        return sum(d for tp, d in D["protocolos"][k][1] if tp == "camara")

    while pend:
        c = int(np.argmin(libre))
        T = libre[c]
        ok = [k for k in pend if T - pre(k) >= t_abre]
        k = max(ok, key=pre) if ok else min(pend, key=pre)
        lleg = max(t_abre, T - pre(k))
        out.append((k, lleg))
        libre[c] = max(T, lleg + pre(k)) + cam(k)
        pend.remove(k)
    return out


def sim_gammacamara(par: dict, D: dict, rng, camaras=None) -> dict:
    import simpy
    env = simpy.Environment()
    camaras = camaras or par["camaras"]
    cam = simpy.Resource(env, camaras)
    iny = simpy.Resource(env, 1)
    esf = simpy.Resource(env, 1)
    espera = Ocupacion(env)
    nombres = list(D["protocolos"])
    fr = np.array([D["protocolos"][k][0] for k in nombres], dtype=float)
    fr /= fr.sum()
    n = par["pacientes_dia"]
    prot = list(rng.choice(nombres, size=n, p=fr))
    # primero los de espera larga (óseo), luego el resto
    prot.sort(key=lambda k: -sum(s[1] for s in D["protocolos"][k][1] if s[0] == "espera"))
    j0, j1 = a_min(par["jornada"][0]), a_min(par["jornada"][1])
    t_cam = [sum(s[1] for s in D["protocolos"][k][1] if s[0] == "camara") for k in prot]
    # agenda: llegada espaciada para que la cámara reciba carga uniforme
    agenda = agenda_gammacamara(prot, D, camaras)
    m = dict(ocup=0.0, fin=[], espera_cam=[])

    def paciente(k, t_lleg):
        yield env.timeout(t_lleg)
        espera.cambio(1 + D["acompanantes"])
        for tipo, dur in D["protocolos"][k][1]:
            if tipo == "iny":
                with iny.request() as r:
                    yield r
                    yield env.timeout(dur)
            elif tipo == "espera":
                yield env.timeout(dur)
            elif tipo == "esfuerzo":
                with esf.request() as r:
                    yield r
                    yield env.timeout(dur)
            else:
                t0 = env.now
                with cam.request() as r:
                    yield r
                    m["espera_cam"].append(env.now - t0)
                    d = dur * float(rng.uniform(0.9, 1.15))
                    yield env.timeout(d)
                    m["ocup"] += d
        espera.cambio(-1 - D["acompanantes"])
        m["fin"].append(env.now)

    for k, t_lleg in agenda:
        env.process(paciente(k, t_lleg))
    env.run()
    return dict(util_gc=m["ocup"] / (camaras * (j1 - j0)), extra_gc_min=max(0.0, max(m["fin"]) - j1),
                espera_cam_media=float(np.mean(m["espera_cam"])), pico_espera_gc=espera.pico,
                minutos_camara=sum(t_cam))


def sim_i131(par: dict, D: dict, rng) -> dict:
    """Ocupación semanal de cuartos de terapia con I-131 (estancia + descontaminación)."""
    semanas = D["semanas"]
    ocupado = np.zeros(semanas * 7 + 14)
    estancias = []
    for w in range(semanas):
        for k in range(par["pacientes_semana"]):
            dia = w * 7 + par["dias_ingreso"][k % len(par["dias_ingreso"])]
            noches = int(rng.choice(D["estancia_noches"]))
            ocupado[dia: dia + noches + D["descontaminacion_d"]] += 1
            estancias.append(noches)
    return dict(cuartos_pico=int(ocupado.max()), util_cuartos=float(ocupado[:semanas * 7].mean() / par["cuartos"]),
                noches_media=float(np.mean(estancias)) if estancias else 0.0,
                dias_sobrecupo=int((ocupado[:semanas * 7] > par["cuartos"]).sum()))


def simular_escenario(nombre: str, esc: dict, P: dict, R: int) -> dict:
    D = P["des"]
    rng = np.random.default_rng(D["semilla"] + zlib.crc32(nombre.encode()) % 1000)
    res = dict(pet=[], linac=[], gk=[], gc=[])
    for _ in range(R):
        res["pet"].append(sim_pet(esc["pet"], D["pet"], rng))
        res["linac"].append(sim_linac_tc(esc, D["linac"], D["hdr"], rng))
        res["gk"].append(sim_gk(esc["gk"], D["gk"], rng))
        res.setdefault("gkm", []).append(sim_gk(dict(esc["gk"], flujo="mascara"), D["gk"], rng))
        res["gc"].append(sim_gammacamara(esc["gammacamara"], D["gammacamara"], rng))
    agg = {}
    for area, lst in res.items():
        for k in lst[0]:
            vals = np.array([d[k] for d in lst], dtype=float)
            agg[f"{area}.{k}.media"] = float(vals.mean())
            agg[f"{area}.{k}.p95"] = float(np.percentile(vals, 95))
    agg.update({f"i131.{k}": v for k, v in sim_i131(esc["i131"], D["i131"], rng).items()})
    return agg


def minimos_recursos(esc: dict, P: dict, R: int) -> dict:
    """Búsqueda del mínimo de salas de captación, vestidores, asientos y gammacámaras."""
    D = P["des"]
    rng = np.random.default_rng(D["semilla"] + 7)
    par = dict(esc["pet"])
    base = None
    out = {}
    # salas de captación: retraso de inyección p95 <= 10 min y fin de jornada <= referencia + 10 min
    ref = [sim_pet(par, D["pet"], rng, n_salas=30, n_vest=10)["fin"] for _ in range(R)]
    base = float(np.mean(ref))
    for k in range(1, 16):
        rs = [sim_pet(par, D["pet"], rng, n_salas=k, n_vest=10) for _ in range(R)]
        if np.mean([r["retraso_iny_p95"] for r in rs]) <= 10 and np.mean([r["fin"] for r in rs]) <= base + 10:
            out["salas_captacion_min"] = k
            break
    for v in range(1, 10):
        rs = [sim_pet(par, D["pet"], rng, n_salas=out["salas_captacion_min"], n_vest=v) for _ in range(R)]
        if np.mean([r["espera_vest_p95"] for r in rs]) <= 5:
            out["vestidores_min"] = v
            out["asientos_espera_pet_p95"] = int(math.ceil(np.percentile([r["pico_espera"] for r in rs], 95)))
            break
    for c in range(1, 6):
        rs = [sim_gammacamara(esc["gammacamara"], D["gammacamara"], rng, camaras=c) for _ in range(R)]
        if np.percentile([r["extra_gc_min"] for r in rs], 95) <= 30:
            out["gammacamaras_min"] = c
            out["asientos_espera_gc_p95"] = int(math.ceil(np.percentile([r["pico_espera_gc"] for r in rs], 95)))
            break
    else:
        out["gammacamaras_min"] = ">5"
    return out


# --------------------------------------------------------------------------------------------
# Personal (referencia OIEA, orientativa)
# --------------------------------------------------------------------------------------------


PUESTOS = {"fisico": "Físico médico", "neurocirujano": "Neurocirujano", "enfermeria": "Enfermería", "tecnologo": "Tecnólogo",
           "oncologo": "Radio-oncólogo", "anestesiologo": "Anestesiólogo", "rtt": "Técnico radioterapeuta (RTT)",
           "operador_ciclotron": "Operador de ciclotrón", "radioquimico": "Radioquímico", "analista_cc": "Analista de control de calidad"}


def personal(esc: dict, plan: dict, minimos: dict, P: dict) -> list[dict]:
    S, D = P["personal"], P["des"]
    dias = S["dias_laborales_anio"]
    L = esc["linac"]
    nuevos_anio = L["fracciones_dia"] / D["linac"]["fracciones_por_curso"] * dias
    nuevos_anio += esc["hdr"]["pacientes_dia"] / 4 * dias   # HDR ~4 fx/curso; GK tiene equipo propio
    unidades_mv = L["unidades"]
    filas = []

    def f(area, puesto, n, base):
        filas.append(dict(area=area, puesto=puesto, personas=int(math.ceil(n - 1e-9)), base=base))

    f("Radioterapia", "Técnico radioterapeuta (RTT)", S["rtt_por_unidad_turno"] * unidades_mv * L["turnos"] + 1, "2 por unidad y turno + 1 TC simulador")
    f("Radioterapia", "Físico médico RT", max(S["fisico_rt_por_unidad"] * (unidades_mv + 2), nuevos_anio / S["fisico_rt_por_pacientes_nuevos_anio"]) + (L["turnos"] - 1), "1 por unidad (linac, GK, HDR) o 1/450 nuevos/año; +1 por turno extra")
    f("Radioterapia", "Dosimetrista", nuevos_anio / S["dosimetrista_por_pacientes_nuevos_anio"], "1 por 300 nuevos/año")
    f("Radioterapia", "Radio-oncólogo", nuevos_anio / S["oncologo_por_pacientes_nuevos_anio"], "1 por 250 nuevos/año")
    f("Radioterapia", "Ingeniero de mantenimiento MV", (unidades_mv + 1) / S["ingeniero_por_unidades_mv"], "1 por 2 unidades (linac + GK)")
    for k, v in S["gk_por_unidad"].items():
        f("Gamma Knife", PUESTOS.get(k, k), v + (1 if k == "fisico" and esc["gk"]["pacientes_dia"] > 5 else 0), "por unidad (+1 físico si > 5 pac/día)")
    for k, v in S["hdr_por_unidad"].items():
        f("HDR", PUESTOS.get(k, k), v, "por unidad")
    pet = esc["pet"]
    turnos_pet = 1
    f("PET/CT", "Tecnólogo PET/CT", S["tecnologo_pet_por_escaner_turno"] * pet["escaneres"] * turnos_pet, "2 por escáner y turno")
    f("PET/CT", "Enfermería (inyección)", max(1, minimos.get("salas_captacion_min", pet["salas_captacion"]) / S["enfermeria_pet_por_salas_captacion"]), "1 por 4 salas de captación")
    gc = esc["gammacamara"]
    cams = minimos.get("gammacamaras_min", gc["camaras"])
    cams = cams if isinstance(cams, int) else 6
    f("Medicina nuclear", "Tecnólogo gammacámara", S["tecnologo_gc_por_camara_turno"] * cams, "1.5 por cámara y turno")
    f("Medicina nuclear", "Médico nuclear", (pet["pacientes_dia"] + gc["pacientes_dia"]) / S["medico_nuclear_por_estudios_dia"], "1 por 25 estudios/día")
    f("Medicina nuclear", "Físico médico MN", (pet["escaneres"] + cams + 1) / S["fisico_mn_por_equipos"], "1 por 4 equipos")
    span = (plan["corridas"][-1].liberacion + 30 - plan["inicio_operacion"]) / 60.0
    turnos_rf = max(1, math.ceil(span / 8.0))
    for k, v in S["radiofarmacia_por_turno"].items():
        f("Ciclotrón/radiofarmacia", PUESTOS.get(k, k), v * turnos_rf, f"{turnos_rf} turno(s) para {span:.1f} h de producción")
    rutas = sum(len(cr.destinos) for cr in plan["corridas"])
    f("Ciclotrón/radiofarmacia", "Responsable sanitario (QP)", 1, "liberación de lotes")
    f("Ciclotrón/radiofarmacia", "Ingeniero de ciclotrón", 1, "mantenimiento")
    f("Ciclotrón/radiofarmacia", "Chofer de distribución", rutas * S["radiofarmacia_fijo"]["logistica_choferes_por_ruta"], f"{rutas} rutas/día")
    return filas


# --------------------------------------------------------------------------------------------
# 3. Cargas de trabajo frente al diseño del blindaje
# --------------------------------------------------------------------------------------------


def tg108_sala_captacion(A0_MBq: float, tU_h: float, t12_h: float, gamma: float) -> float:
    """Dosis a 1 m por paciente en sala de captación (uSv), AAPM TG-108 ec. 3-4."""
    R = 1.443 * (t12_h / tU_h) * (1 - math.exp(-LN2 * tU_h / t12_h))
    return gamma * A0_MBq * tU_h * R


def tg108_sala_escaner(A0_MBq: float, tU_h: float, tI_h: float, t12_h: float, gamma: float, fv: float) -> float:
    """Dosis a 1 m por paciente en sala del tomógrafo (uSv), TG-108 con vaciado de vejiga."""
    FU = math.exp(-LN2 * tU_h / t12_h)
    R = 1.443 * (t12_h / tI_h) * (1 - math.exp(-LN2 * tI_h / t12_h))
    return gamma * A0_MBq * fv * FU * tI_h * R


def cargas_vs_diseno(nombre: str, esc: dict, plan: dict, cu: dict, ga: dict, minimos: dict, P: dict) -> list[dict]:
    Dz, ds = P["diseno_blindaje"], P["diseno_blindaje"]["dias_semana"]
    filas = []

    def fila(area, magnitud, valor, diseno, unidad, nota=""):
        r = valor / diseno if diseno else float("nan")
        filas.append(dict(escenario=nombre, area=area, magnitud=magnitud, valor=round(valor, 2), diseno=round(diseno, 2),
                          unidad=unidad, razon=round(r, 2), excede=bool(r > 1.0 + 1e-9), nota=nota))

    L = Dz["linac"]
    W = esc["linac"]["fracciones_dia"] * L["dosis_fx_Gy"] * ds
    WL = W * ((1 - L["fraccion_IMRT"]) + L["fraccion_IMRT"] * L["factor_IMRT"])
    fila("Linac", "W primaria (isocentro)", W, L["W_Gy_sem"], "Gy/sem", L["base"])
    extra = L["TVL_fuga_hormigon_cm"] * math.log10(WL / L["W_Gy_sem"]) if WL > L["W_Gy_sem"] else 0.0
    fila("Linac", f"W fuga (IMRT x{L['factor_IMRT']:g})", WL, L["W_Gy_sem"], "Gy/sem",
         f"barreras secundarias: +{extra:.0f} cm de hormigón 2.35 si el diseño usó 900 Gy sin factor IMRT")
    pet = esc["pet"]
    Tp = Dz["pet"]
    t12h = P["fisica"]["t12_min"]["F18"] / 60
    g, fv = Dz["tg108"]["gamma_uSv_m2_MBq_h"], Dz["tg108"]["factor_vaciado"]
    n_sem = pet["pacientes_dia"] * ds
    fila("PET/CT", "pacientes/semana", n_sem, Tp["pacientes_sem"], "pac/sem", Tp["base"])
    for A0 in (370.0, 555.0):
        fila("PET/CT", f"actividad inyectada semanal (A0={A0:.0f} MBq)", n_sem * A0 / 1000, Tp["pacientes_sem"] * Tp["A0_MBq"] / 1000, "GBq/sem")
        salas = max(minimos.get("salas_captacion_min", pet["salas_captacion"]), Tp["salas_captacion"])
        d_s = n_sem / salas * tg108_sala_captacion(A0, Tp["t_captacion_h"], t12h, g)
        d_d = Tp["pacientes_sem"] / Tp["salas_captacion"] * tg108_sala_captacion(Tp["A0_MBq"], Tp["t_captacion_h"], t12h, g)
        fila("PET/CT", f"TG-108 sala de captación a 1 m (A0={A0:.0f}, {salas} salas)", d_s / 1000, d_d / 1000, "mSv/sem")
        tI = np.mean(P["des"]["pet"]["escaneo_min"]) / 60
        d_e = n_sem / pet["escaneres"] * tg108_sala_escaner(A0, Tp["t_captacion_h"], tI, t12h, g, fv)
        d_ed = Tp["pacientes_sem"] / Tp["escaneres"] * tg108_sala_escaner(Tp["A0_MBq"], Tp["t_captacion_h"], Tp["t_escaneo_h"], t12h, g, fv)
        fila("PET/CT", f"TG-108 sala del tomógrafo a 1 m (A0={A0:.0f}, {pet['escaneres']} escáner)", d_e / 1000, d_ed / 1000, "mSv/sem",
             "2.º escáner sin diseño de blindaje" if pet["escaneres"] > Tp["escaneres"] else "")
    if minimos.get("salas_captacion_min", 0) > Tp["salas_captacion"]:
        fila("PET/CT", "salas de captación requeridas", minimos["salas_captacion_min"], Tp["salas_captacion"], "salas",
             "salas adicionales sin diseño de blindaje")
    I = Dz["i131"]
    fila("I-131", "pacientes/semana", esc["i131"]["pacientes_semana"], I["pacientes_sem"], "pac/sem", I["base"])
    fila("I-131", "actividad semanal administrada", esc["i131"]["pacientes_semana"] * I["A_GBq"], I["pacientes_sem"] * I["A_GBq"], "GBq/sem")
    fila("HDR", "pacientes/semana", esc["hdr"]["pacientes_dia"] * ds, Dz["hdr"]["pacientes_sem"], "pac/sem", Dz["hdr"]["base"])
    fila("Gamma Knife", "pacientes/semana", esc["gk"]["pacientes_dia"] * ds, Dz["gk"]["pacientes_sem"], "pac/sem", Dz["gk"]["base"])
    fila("Gammacámara", "pacientes/semana", esc["gammacamara"]["pacientes_dia"] * ds, Dz["gammacamara"]["pacientes_sem"], "pac/sem", Dz["gammacamara"]["base"])
    nuevos = esc["linac"]["fracciones_dia"] / P["des"]["linac"]["fracciones_por_curso"]
    fila("TC simulador", "estudios/semana", (nuevos + esc["hdr"]["pacientes_dia"]) * ds, Dz["tc_simulador"]["pacientes_sem"], "est/sem", Dz["tc_simulador"]["base"])
    cy = P["ciclotron"]
    uah = plan["uAh_dia"] * ds + cu["uAh_lote"]
    fila("Ciclotrón", "carga integrada", uah, cy["presupuesto_uAh_semana"], "uA·h/sem", "presupuesto_operativo@1")
    imax = max(cr.I_blanco for cr in plan["corridas"]) * cy["blancos_F18"]
    fila("Ciclotrón", "corriente máxima", imax, cy["corriente_max_total_uA"], "uA")
    h_cu = P["cobre64"]["t_irr_min"] / 60 / ds if cu["pacientes_semana"] > 0 else 0.0
    fila("Ciclotrón", "horas de haz por día (FDG + Cu-64 prorrateado)", plan["horas_haz_dia"] + h_cu,
         cy["horas_haz_dia_diseno_GAMMA"], "h/día", "estimación GAMMA (8 h/día a 300 uA)")
    return filas


# --------------------------------------------------------------------------------------------
# Gráficas (paleta categórica de referencia, orden fijo)
# --------------------------------------------------------------------------------------------

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
ESTADO = {"bien": "#0ca30c", "aviso": "#fab219", "serio": "#ec835a", "critico": "#d03b3b"}
TINTA, TINTA2, REJILLA, FONDO = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def _estilo(plt):
    plt.rcParams.update({"figure.facecolor": FONDO, "axes.facecolor": FONDO, "axes.edgecolor": REJILLA,
                         "axes.labelcolor": TINTA2, "xtick.color": TINTA2, "ytick.color": TINTA2,
                         "text.color": TINTA, "axes.grid": True, "grid.color": REJILLA, "grid.linewidth": 0.6,
                         "axes.spines.top": False, "axes.spines.right": False, "font.size": 9})


def grafica_gantt(nombre: str, plan: dict, ga: dict, P: dict, ruta: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _estilo(plt)
    rf, cy = plan["P"]["radiofarmacia"], P["ciclotron"]
    filas, barras = [], []

    def barra(fila, t0, t1, color, txt="", dentro=False, alfa=1.0):
        if fila not in filas:
            filas.append(fila)
        barras.append((fila, t0, t1, color, txt, dentro, alfa))

    for k, cr in enumerate(plan["corridas"]):
        T = cr.tiempos(plan["P"])
        c = SERIES[k]
        if k == 0:
            barra("Ciclotrón: arranque", plan["inicio_operacion"], T["SOB"], "#9b9a95", "arranque")
        barra("Ciclotrón: haz (T1+T5)", T["SOB"], T["EOB"], c, f"{cr.I_blanco * cy['blancos_F18']:.0f} µA")
        barra("Síntesis FDG (Synthera+)", T["ini_sintesis"], T["EOS"], c)
        barra("Control de calidad", T["EOS"], T["liberacion"], c)
        if cr.demanda_local:
            barra("PET local: inyecciones FDG", min(cr.demanda_local), max(cr.demanda_local) + 5, c, f"{len(cr.demanda_local)}", dentro=True)
        for d in cr.destinos:
            barra(f"Ruta → {d['ciudad']}", d["_salida"], d["_llegada"], c)
            if d["_tiempos"]:
                barra(f"Ruta → {d['ciudad']}", d["_tiempos"][0], d["_tiempos"][-1] + 5, c,
                      f"{d['dosis_entregables']}/{d['dosis_solicitadas']} dosis", alfa=0.45)
    for lo in ga["lotes"]:
        barra("Ga-68: elución + marcaje + QC", lo["elucion"], lo["liberacion"], SERIES[6], f"{lo['pacientes']} pac")
    fig, ax = plt.subplots(figsize=(11, 0.42 * len(filas) + 1.6))
    for fila, t0, t1, color, txt, dentro, alfa in barras:
        y = filas.index(fila)
        ax.barh(y, (t1 - t0) / 60, left=t0 / 60, height=0.55, color=color, alpha=alfa, edgecolor=FONDO, linewidth=2)
        if txt and dentro:
            ax.text((t0 + t1) / 120, y, txt, va="center", ha="center", fontsize=7.5, color=FONDO, weight="bold")
        elif txt:
            ax.text(t1 / 60 + 0.05, y, txt, va="center", fontsize=7.5, color=TINTA2)
    ax.set_yticks(range(len(filas)))
    ax.set_yticklabels(filas)
    ax.invert_yaxis()
    lo = math.floor(min(b[1] for b in barras) / 60) - 0.5
    hi = math.ceil(max(b[2] for b in barras) / 60) + 1.5
    ax.set_xlim(lo, hi)
    xt = np.arange(math.ceil(lo), hi + 0.01, 1)
    ax.set_xticks(xt)
    ax.set_xticklabels([f"{int(x) % 24:02d}:00" for x in xt])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Hora del día")
    ax.set_title(f"Programa diario de producción y distribución — {nombre} (inicio de operación {a_hhmm(plan['inicio_operacion'])})\n"
                 "Rutas: barra sólida = traslado; barra clara = ventana de inyecciones en destino. PET local: número de dosis FDG.",
                 loc="left", fontsize=10.5)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=SERIES[k], label=cr.nombre) for k, cr in enumerate(plan["corridas"])] + [Patch(color=SERIES[6], label="Ga-68 generador")],
              loc="lower right", frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def grafica_disponibilidad(nombre: str, plan: dict, ga: dict, cu: dict, P: dict, ruta: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _estilo(plt)
    Pp = plan["P"]
    rf, t12 = Pp["radiofarmacia"], P["fisica"]["t12_min"]
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.8), gridspec_kw=dict(width_ratios=[2.2, 1.2, 1.2]))
    ax = axs[0]
    A0 = plan["A0"]
    for k, cr in enumerate(plan["corridas"]):
        T = cr.tiempos(Pp)
        retiros = [(t - rf["dispensacion_min"], A0 * rf["margen_dispensacion"] * math.exp(constante_decaimiento(t12["F18"]) * rf["dispensacion_min"]) / 1000) for t in cr.demanda_local]
        for d in cr.destinos:
            retiros.append((d["_salida"], decaer(d["A_EOS_GBq"], d["_salida"] - T["EOS"], t12["F18"])))
        retiros.sort()
        ts = np.arange(T["EOS"], T["EOS"] + 10 * 60, 2.0)
        A = []
        for t in ts:
            a = decaer(cr.A_EOS, t - T["EOS"], t12["F18"]) - sum(decaer(v, t - tr, t12["F18"]) for tr, v in retiros if tr <= t)
            A.append(max(a, 0))
        ax.plot(ts / 60, A, color=SERIES[k], lw=2, label=f"{cr.nombre}: EOS {a_hhmm(T['EOS'])}, {cr.A_EOS:.0f} GBq")
    ax.set_title("F-18 FDG disponible en la radiofarmacia (corregido por decaimiento)", loc="left", fontsize=9.5)
    ax.set_ylabel("GBq")
    xt = ax.get_xticks()
    ax.set_xticks(xt)
    ax.set_xticklabels([f"{int(x) % 24:02d}:00" for x in xt])
    ax.legend(frameon=False, fontsize=7.5)
    ax = axs[1]
    for lo in ga["lotes"]:
        ts = np.arange(lo["liberacion"], lo["liberacion"] + 180, 2.0)
        ax.plot(ts / 60, [decaer(lo["A_liberacion_GBq"], t - lo["liberacion"], t12["Ga68"]) * 1000 for t in ts], color=SERIES[6], lw=2)
        ax.text(lo["liberacion"] / 60, lo["A_liberacion_GBq"] * 1000, f" {lo['pacientes']} pac", fontsize=7.5, color=TINTA2)
    ax.axhline(P["galio68"]["dosis_MBq"], color=TINTA2, lw=1, ls="--")
    ax.text(ax.get_xlim()[0], P["galio68"]["dosis_MBq"], "1 dosis", fontsize=7.5, color=TINTA2, va="bottom")
    ax.set_title(f"Ga-68 por elución (Ge-68 {ga['A_Ge68_GBq']:.2f} GBq)", loc="left", fontsize=9.5)
    ax.set_ylabel("MBq")
    xt = ax.get_xticks()
    ax.set_xticks(xt)
    ax.set_xticklabels([f"{int(x) % 24:02d}:00" for x in xt])
    ax = axs[2]
    hs = np.arange(0, 96, 0.5)
    ax.plot(hs, [decaer(cu["A_liberacion_GBq"], h * 60, t12["Cu64"]) for h in hs], color=SERIES[4], lw=2)
    ax.axhline(P["cobre64"]["dosis_MBq"] / 1000, color=TINTA2, lw=1, ls="--")
    ax.set_title(f"Cu-64 por lote semanal ({cu['A_liberacion_GBq']:.1f} GBq)", loc="left", fontsize=9.5)
    ax.set_xlabel("horas desde la liberación")
    ax.set_ylabel("GBq")
    fig.suptitle(f"Curvas de disponibilidad — {nombre}", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def grafica_mapa(tablas: dict, P: dict, ruta: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _estilo(plt)
    ciudades = P["distribucion"]["ciudades"]
    o = P["distribucion"]["origen"]
    nombres = list(tablas)
    fig, axs = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw=dict(width_ratios=[1.15, 1]))
    ax = axs[0]
    ultimo = tablas[nombres[-1]]
    estado = {}
    for c in ciudades:
        filas = [r for r in ultimo if r["ciudad"] == c["nombre"]]
        if any(r["factible"] for r in filas):
            estado[c["nombre"]] = ("bien", "factible (corrida regular)")
        elif any(r["dosis_entregables"] > 0 for r in filas):
            estado[c["nombre"]] = ("aviso", "parcial")
        else:
            estado[c["nombre"]] = ("critico", "no factible")
    for c in ciudades:
        e = estado[c["nombre"]][0]
        ax.plot([o["lon"], c["lon"]], [o["lat"], c["lat"]], color=REJILLA, lw=1.5, zorder=1)
        ax.scatter(c["lon"], c["lat"], s=110, color=ESTADO[e], edgecolor=FONDO, linewidth=2, zorder=3)
        sim = {"bien": "✓", "aviso": "~", "critico": "✗"}[e]
        ax.annotate(f"{sim} {c['nombre']}\n{c['km']} km · {tiempo_traslado(c['km'], P['distribucion']['velocidad_kmh'], P['distribucion']['parada_min_cada_4h']) / 60:.1f} h",
                    (c["lon"], c["lat"]), xytext=(6, 6), textcoords="offset points", fontsize=8, color=TINTA)
    ax.scatter(o["lon"], o["lat"], s=160, marker="*", color=TINTA, zorder=4)
    ax.annotate("Zumaya (Villahermosa)", (o["lon"], o["lat"]), xytext=(6, -12), textcoords="offset points", fontsize=8.5, weight="bold")
    ax.set_xlabel("longitud")
    ax.set_ylabel("latitud")
    ax.set_aspect("equal")
    ax.set_title(f"Factibilidad con corridas regulares — {nombres[-1]}\n✓ factible  ~ parcial  ✗ no factible", loc="left", fontsize=9.5)
    # matriz ciudad x (escenario, corrida): dosis entregadas / solicitadas
    ax = axs[1]
    cols = []
    for n in nombres:
        for cr in sorted({r["corrida"] for r in tablas[n]}):
            cols.append((n, cr))
    M = np.zeros((len(ciudades), len(cols)))
    for j, (n, cr) in enumerate(cols):
        for i, c in enumerate(ciudades):
            r = next(r for r in tablas[n] if r["ciudad"] == c["nombre"] and r["corrida"] == cr)
            M[i, j] = r["dosis_entregables"] / r["dosis_solicitadas"]
            txt = "✓" if r["factible"] else (f"{r['dosis_entregables']}/{r['dosis_solicitadas']}" if r["dosis_entregables"] else "✗")
            ax.text(j, i, txt, ha="center", va="center", fontsize=7.5, color=FONDO if M[i, j] > 0.55 else TINTA)
    from matplotlib.colors import LinearSegmentedColormap
    cm = LinearSegmentedColormap.from_list("az", ["#f1f0ec", "#86b6ef", "#1c5cab"])
    ax.imshow(M, cmap=cm, vmin=0, vmax=1, aspect="auto")
    ax.set_yticks(range(len(ciudades)))
    ax.set_yticklabels([c["nombre"] for c in ciudades])
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([f"{n.split('_')[0]}\n{cr.replace('Corrida ', 'C')}" for n, cr in cols], fontsize=7.5)
    ax.grid(False)
    ax.set_title("Fracción de dosis entregables por corrida (✓ = todas)", loc="left", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def grafica_utilizacion(util: list[dict], ruta: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _estilo(plt)
    recursos = list(dict.fromkeys(u["recurso"] for u in util))
    escs = list(dict.fromkeys(u["escenario"] for u in util))
    fig, ax = plt.subplots(figsize=(12, 4.6))
    w = 0.8 / len(escs)
    for k, e in enumerate(escs):
        vals = [next((u["utilizacion"] for u in util if u["escenario"] == e and u["recurso"] == r), 0) for r in recursos]
        x = np.arange(len(recursos)) + (k - (len(escs) - 1) / 2) * w
        ax.bar(x, np.array(vals) * 100, width=w - 0.04, color=SERIES[k], label=e, edgecolor=FONDO, linewidth=1)
        for xi, v in zip(x, vals):
            if v > 0.85:
                ax.text(xi, v * 100 + 2, f"{v * 100:.0f}", ha="center", fontsize=7, color=TINTA)
    ax.axhline(85, color=ESTADO["critico"], lw=1, ls="--")
    ax.text(-0.45, 87, "85 % (umbral de cuello de botella)", ha="left", va="bottom", fontsize=7.5, color=TINTA2)
    ax.set_xticks(range(len(recursos)))
    ax.set_xticklabels(recursos, rotation=20, ha="right")
    ax.set_ylabel("Utilización de la jornada (%)")
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, ncol=3, loc="upper center")
    ax.set_title("Utilización por área y equipo (media de réplicas; >100 % = tiempo extra)", loc="left", fontsize=10.5)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


# --------------------------------------------------------------------------------------------
# Orquestación
# --------------------------------------------------------------------------------------------


def cargar(ruta: Path = AQUI / "escenarios.yaml") -> dict:
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _csv(filas: list[dict], ruta: Path):
    import csv
    if not filas:
        return
    claves = list(dict.fromkeys(k for f in filas for k in f if not k.startswith("_")))
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=claves, extrasaction="ignore")
        w.writeheader()
        for f in filas:
            w.writerow({k: v for k, v in f.items() if not k.startswith("_")})


def ejecutar(replicas: int | None = None, salida: Path = AQUI / "resultados") -> dict:
    P = cargar()
    R = replicas or P["des"]["replicas"]
    salida.mkdir(parents=True, exist_ok=True)
    resumen, tablas, util, cargas, pers, prod, mins, esperas, sens, dedic = {}, {}, [], [], [], [], [], [], [], []
    for nombre, esc in P["escenarios"].items():
        plan = planificar_produccion(esc, P)
        for caso, ov in P["radiofarmacia"]["sensibilidad"].items():
            pl = planificar_produccion(esc, P, ov)
            sens.append(dict(escenario=nombre, caso=caso, **ov, inicio_operacion=a_hhmm(pl["inicio_operacion"]),
                             inicio_operacion_a_300uA=a_hhmm(pl["inicio_operacion_300uA"]),
                             A_EOS_corrida1_GBq=round(pl["corridas"][0].A_EOS, 1)))
        ga = plan_galio68(plan["t_ga"], P)
        cu = plan_cobre64(esc["cu64"]["pacientes_semana"], P)
        tablas[nombre] = plan["tabla_factibilidad"]
        for cr in plan["corridas"]:
            T = cr.tiempos(plan["P"])
            prod.append(dict(escenario=nombre, corrida=cr.nombre, inicio_haz=a_hhmm(T["SOB"]), EOB=a_hhmm(T["EOB"]),
                             EOS=a_hhmm(T["EOS"]), liberacion=a_hhmm(T["liberacion"]), corriente_total_uA=cr.I_blanco * P["ciclotron"]["blancos_F18"],
                             t_irr_min=round(cr.t_irr, 1), uAh=round(cr.I_blanco * P["ciclotron"]["blancos_F18"] * cr.t_irr / 60, 1),
                             A_EOB_GBq=round(cr.A_EOB, 1), A_EOS_GBq=round(cr.A_EOS, 1), A_EOS_requerida_GBq=round(cr.A_EOS_req, 1),
                             dosis_locales=len(cr.demanda_local), destinos="; ".join(f"{d['ciudad']} ({d['dosis_entregables']}/{d['dosis_solicitadas']})" for d in cr.destinos),
                             alerta=cr.alerta.strip(" |")))
        for c in P["distribucion"]["ciudades"]:
            r = corrida_dedicada(c, plan["pedidos"][c["nombre"]], plan["P"])
            dedic.append(dict(escenario=nombre, **{k: v for k, v in r.items() if not k.startswith("_")}))
        grafica_gantt(nombre, plan, ga, P, salida / f"gantt_produccion_{nombre}.png")
        grafica_disponibilidad(nombre, plan, ga, cu, P, salida / f"curvas_disponibilidad_{nombre}.png")
        # DES
        agg = simular_escenario(nombre, esc, P, R)
        mn = minimos_recursos(esc, P, max(10, R // 3))
        mins.append(dict(escenario=nombre, **mn, cuartos_I131_pico=agg["i131.cuartos_pico"]))
        U = [("Tomógrafo PET/CT", agg["pet.util_escaner.media"]), ("Salas de captación PET", agg["pet.util_salas.media"]),
             ("Acelerador (clínico)", agg["linac.util_linac.media"]), ("Acelerador (clínico + QA)", agg["linac.util_linac_con_QA.media"]),
             ("TC simulador", agg["linac.util_tc.media"]), ("Gamma Knife", agg["gk.util_gk.media"]), ("RM (flujo GK)", agg["gk.util_rm_gk.media"]),
             ("HDR (Flexitron)", agg["linac.util_hdr.media"]), ("Sala de procedimientos HDR", agg["linac.util_sala_proc_hdr.media"]),
             ("Gammacámara", agg["gc.util_gc.media"]), ("Cuartos I-131", agg["i131.util_cuartos"])]
        for r, v in U:
            util.append(dict(escenario=nombre, recurso=r, utilizacion=round(v, 3), cuello_de_botella=v > 0.85))
        esperas.append(dict(escenario=nombre,
                            pet_espera_sala_captacion_min=round(agg["pet.espera_sala_media.media"], 1),
                            pet_retraso_inyeccion_p95_min=round(agg["pet.retraso_iny_p95.media"], 1),
                            pet_espera_escaner_min=round(agg["pet.espera_escaner_media.media"], 1),
                            pet_fin_jornada=a_hhmm(agg["pet.fin.media"]), pet_tiempo_extra_min=round(agg["pet.extra_min.media"], 0),
                            linac_espera_media_min=round(agg["linac.espera_linac_media.media"], 1), linac_espera_p95_min=round(agg["linac.espera_linac_p95.media"], 1),
                            linac_tiempo_extra_min=round(agg["linac.extra_linac_min.media"], 0),
                            gk_fin=a_hhmm(agg["gk.fin_gk.media"]), gk_tiempo_extra_min=round(agg["gk.extra_gk_min.media"], 0),
                            gk_espera_equipo_min=round(agg["gk.espera_gk_media.media"], 1),
                            gk_fin_con_mascara_y_planeacion_previa=a_hhmm(agg["gkm.fin_gk.media"]),
                            gk_tiempo_extra_con_mascara_min=round(agg["gkm.extra_gk_min.media"], 0),
                            hdr_ciclo_h=round(agg["linac.ciclo_hdr_h.media"], 2), hdr_espera_TC_min=round(agg["linac.espera_tc_hdr_media.media"], 1),
                            hdr_tiempo_extra_min=round(agg["linac.extra_hdr_min.media"], 0),
                            gc_espera_camara_min=round(agg["gc.espera_cam_media.media"], 1), gc_tiempo_extra_min=round(agg["gc.extra_gc_min.media"], 0),
                            i131_cuartos_pico=agg["i131.cuartos_pico"], i131_dias_sobrecupo_anio=agg["i131.dias_sobrecupo"],
                            asientos_espera_linac_p95=int(math.ceil(agg["linac.pico_espera_linac.p95"]))))
        for f in personal(esc, plan, mn, P):
            pers.append(dict(escenario=nombre, **f))
        cargas += cargas_vs_diseno(nombre, esc, plan, cu, ga, mn, P)
        resumen[nombre] = dict(inicio_operacion=a_hhmm(plan["inicio_operacion"]),
                               inicio_operacion_a_300uA=a_hhmm(plan["inicio_operacion_300uA"]), uAh_dia=round(plan["uAh_dia"], 1),
                               horas_haz_dia=round(plan["horas_haz_dia"], 2),
                               ciudades_factibles=sorted({d["ciudad"] for cr in plan["corridas"] for d in cr.destinos if d["factible"]}),
                               ciudades_parciales=sorted({d["ciudad"] for cr in plan["corridas"] for d in cr.destinos if d["parcial"]}),
                               ga68={"lotes": [dict(elucion=a_hhmm(lo["elucion"]), A_GBq=round(lo["A_liberacion_GBq"], 2), pacientes=lo["pacientes"]) for lo in ga["lotes"]],
                                     "no_atendidos": ga["no_atendidos"],
                                     "blanco_liquido": {k: round(v, 2) for k, v in ga["blanco_liquido"].items()}},
                               cu64={k: round(v, 2) if isinstance(v, float) else v for k, v in cu.items()},
                               minimos=mn, cuellos_de_botella=[u["recurso"] for u in util if u["escenario"] == nombre and u["cuello_de_botella"]],
                               excede_diseno=[f"{c['area']}: {c['magnitud']} ({c['razon']}x)" for c in cargas if c["escenario"] == nombre and c["excede"]])
    _csv(prod, salida / "produccion_corridas.csv")
    _csv([dict(escenario=n, **r) for n, t in tablas.items() for r in t], salida / "factibilidad_distribucion.csv")
    _csv(dedic, salida / "corrida_dedicada_por_ciudad.csv")
    _csv(sens, salida / "sensibilidad_inicio_operacion.csv")
    _csv(util, salida / "utilizacion.csv")
    _csv(esperas, salida / "esperas_y_tiempo_extra.csv")
    _csv(mins, salida / "minimos_recursos.csv")
    _csv(pers, salida / "personal.csv")
    _csv(cargas, salida / "cargas_vs_diseno_blindaje.csv")
    grafica_mapa(tablas, P, salida / "mapa_factibilidad_distribucion.png")
    grafica_utilizacion(util, salida / "utilizacion_por_area.png")
    with open(salida / "resumen.json", "w", encoding="utf-8") as fh:
        json.dump(dict(replicas=R, escenarios=resumen), fh, ensure_ascii=False, indent=1, default=str)
    return resumen


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Modelo operacional Zumaya")
    ap.add_argument("--replicas", type=int, default=None)
    ap.add_argument("--salida", type=Path, default=AQUI / "resultados")
    a = ap.parse_args()
    res = ejecutar(a.replicas, a.salida)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
