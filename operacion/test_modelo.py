"""Pruebas de la matemática de decaimiento, producción y entrega del modelo operacional."""
import math

import numpy as np
import pytest

import modelo as m

T12 = 109.77


@pytest.fixture(scope="module")
def P():
    return m.cargar()


def test_decaimiento_media_vida():
    assert m.decaer(100.0, T12, T12) == pytest.approx(50.0)
    assert m.decaer(100.0, 2 * T12, T12) == pytest.approx(25.0)
    assert m.decaer(100.0, -T12, T12) == pytest.approx(200.0)


def test_actividad_requerida_una_y_varias_dosis():
    # una dosis de 370 MBq una media vida después necesita 740 MBq ahora
    assert m.actividad_requerida(370, [T12], 0.0, T12) == pytest.approx(740.0)
    # suma de dosis con margen
    A = m.actividad_requerida(370, [0.0, T12, 2 * T12], 0.0, T12, margen=1.1)
    assert A == pytest.approx(1.1 * 370 * (1 + 2 + 4))


def test_irradiacion_inversa_de_eob():
    A = m.actividad_eob(150, 9.29, 75, T12)
    assert m.tiempo_irradiacion(A, 150, 9.29, T12) == pytest.approx(75.0)
    assert m.tiempo_irradiacion(150 * 9.29 * 1.01, 150, 9.29, T12) is None   # por encima de saturación
    assert m.factor_saturacion(T12, T12) == pytest.approx(0.5)


def test_calibracion_ysat_con_dato_IBA():
    # propuesta IBA: 24 Ci (888 GBq) de F-18 en 2 h con 180 uA
    ys = m.ysat_desde_dato_fabricante(888.0, 180.0, 120.0, T12)
    assert ys == pytest.approx(9.29, abs=0.01)
    # coherente con el blanco HCFT-700: 700 GBq en 2 h requieren ~142 uA (< 150 uA por blanco)
    assert 700.0 / (ys * m.factor_saturacion(120, T12)) == pytest.approx(141.8, abs=0.5)


def test_ysat_desde_rendimiento_inicial():
    lam_h = math.log(2) / (T12 / 60)
    assert m.ysat_desde_rendimiento_inicial(5.5, T12) == pytest.approx(5.5 / lam_h)


def test_tiempo_traslado():
    assert m.tiempo_traslado(160, 80) == pytest.approx(120.0)
    assert m.tiempo_traslado(400, 80, 15) == pytest.approx(300.0 + 15.0)


def test_entrega_destino_cercano(P):
    c = {"nombre": "Prueba", "km": 80, "ventana": ["08:00", "15:00"]}
    lib = m.a_min("07:00")
    r = m.factibilidad_destino(c, 3, lib, P)
    rf, di = P["radiofarmacia"], P["distribucion"]
    llegada = lib + rf["embalaje_min"] + 60
    inicio = max(m.a_min("08:00"), llegada + di["recepcion_min"])
    tiempos = [inicio + k * di["intervalo_dosis_min"] for k in range(3)]
    eos = lib - rf["qc_FDG_min"]
    esperado = rf["margen_dispensacion"] * sum(370 * math.exp(math.log(2) / T12 * (t - eos)) for t in tiempos) / 1000
    assert r["factible"]
    assert r["A_EOS_GBq"] == pytest.approx(esperado, abs=0.01)
    assert r["llegada"] == m.a_hhmm(llegada)


def test_destino_lejano_no_factible_por_caducidad(P):
    oax = next(c for c in P["distribucion"]["ciudades"] if c["nombre"] == "Oaxaca")
    r = m.factibilidad_destino(oax, 6, m.a_min("07:00"), P)
    assert not r["factible"] and r["dosis_entregables"] == 0
    # incluso con corrida dedicada la caducidad (EOS + 10 h) llega antes que el vehículo
    d = m.corrida_dedicada(oax, 6, P)
    assert d["dosis_entregables"] == 0


def test_plan_produccion_cadena_temporal(P):
    esc = P["escenarios"]["E1_inicial"]
    plan = m.planificar_produccion(esc, P)
    c1 = plan["corridas"][0]
    T = c1.tiempos(plan["P"])
    rf, cy = P["radiofarmacia"], P["ciclotron"]
    assert T["liberacion"] - T["EOS"] == rf["qc_FDG_min"]
    assert T["EOS"] - T["ini_sintesis"] == rf["sintesis_FDG_min"]
    assert plan["inicio_operacion"] == pytest.approx(T["SOB"] - cy["arranque_min"])
    assert T["liberacion"] <= min(plan["t_fdg"]) - rf["dispensacion_min"]
    # la actividad producida cubre la demanda de cada corrida
    for cr in plan["corridas"]:
        assert cr.A_EOS >= cr.A_EOS_req - 1e-6
        assert cr.I_blanco * cy["blancos_F18"] <= cy["corriente_max_total_uA"]
    # no hay traslape de haz entre corridas
    for a, b in zip(plan["corridas"], plan["corridas"][1:]):
        assert b.tiempos(plan["P"])["SOB"] >= a.tiempos(plan["P"])["EOB"]


def test_tg108_factores():
    # con tU -> 0 el factor de reducción tiende a 1: dosis = Gamma A0 t
    d = m.tg108_sala_captacion(370, 1e-6, T12 / 60, 0.092)
    assert d == pytest.approx(0.092 * 370 * 1e-6, rel=1e-3)   # 1.443 ≈ 1/ln 2
    # TG-108 tabla: R_tU para 60 min de captación = 0.83
    R = m.tg108_sala_captacion(1, 1.0, T12 / 60, 1.0)
    assert R == pytest.approx(0.83, abs=0.01)


def test_galio68_y_cobre64(P):
    ga = m.plan_galio68([m.a_min("08:00"), m.a_min("11:00")], P)
    assert sum(lo["pacientes"] for lo in ga["lotes"]) + ga["no_atendidos"] == 2
    cu = m.plan_cobre64(2, P)
    assert cu["A_EOB_GBq"] > cu["A_liberacion_GBq"] > 0


def test_agenda_gammacamara_completa(P):
    D = P["des"]["gammacamara"]
    prot = ["oseo", "renal", "tiroides", "oseo", "otros"]
    ag = m.agenda_gammacamara(prot, D, 1)
    assert sorted(k for k, _ in ag) == sorted(prot)
    assert all(t >= m.a_min(D["primera_llegada"]) for _, t in ag)


def test_formato_horas():
    assert m.a_hhmm(450) == "07:30"
    assert m.a_hhmm(-30) == "(-1d) 23:30"
    assert m.a_min("02:53") == 173
