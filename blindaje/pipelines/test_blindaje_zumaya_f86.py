"""Pruebas F86 — BD de blindaje Zumaya (densidades IMCYC, linac NCRP 151, ciclotrón losa_tvl)."""
import json, os, pathlib, sys
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import blindaje_zumaya_f86 as F

BD = json.load(open(F.BD))


def test_bd_no_inventa_composicion_ni_tvl():
    for k, m in BD["materiales"].items():
        if k.startswith("tabique_NIPOL"):
            assert m["composicion"].startswith("pendiente_fuente")
            assert m["TVL_proveedor"].startswith("pendiente_fuente")


def test_densidad_real_menor_que_nominal_y_nominal_es_aparente():
    d = F.densidades(BD)
    assert abs(d["tabique_NIPOL_5"]["seca"] - 3.99) < 0.02
    assert abs(d["tabique_NIPOL_5"]["aparente"] - 5.11) < 0.02
    for k, v in d.items():
        assert v["seca"] < v["nominal"] < v["aparente"] * 1.001


def test_linac_reescalado_coherente():
    d = F.densidades(BD)
    L = F.linac(BD, d)
    esc = L["GAMMA_reescalado"]["GAMMA_5.0_calc_x(5.0/real)"]
    assert abs(esc[1] / 75 - 5.0 / d["tabique_NIPOL_5"]["seca"]) < 1e-3
    # lo dibujado (65 cm) construido con tabique 5 real no alcanza el primario NCRP 151 a 6 MV con T=1
    b = L["barreras"]["primario_lateral"]
    assert b["DWG_eq_hormigon_cm_si_NIPOL5"] < b["requerido"]["6MV"]["hormigon_cm"]


@pytest.mark.skipif(not any(F.LOSA.glob("res_ORD_235_s*.txt")), reason="sin corridas losa_tvl en KIUBE_RAIZ")
def test_tvl_hormigon_coherente_con_F85():
    C = F.ciclotron(BD)
    assert 22 < C["ORD_235"]["TVL_cm"] < 32          # F85: 26 cm


# ---------------------------------------------------------------- F87 (adenda: fichas CONTUPLEX y equipos)
import blindaje_zumaya_f87 as F87


def test_f87_td350_medido_coherente_por_masa():
    T = F87.tvl_materiales(BD, F.densidades(BD))
    for e, c in T["chequeo_masico_TD350"].items():
        assert abs(c["TD350_g_cm2"] / c["hormigon_TVLe_g_cm2"] - 1) < 0.12


def test_f87_td500_real_peor_que_ficha():
    T = F87.tvl_materiales(BD, F.densidades(BD))
    assert 1.15 < T["TD-500"]["factor_real_sobre_ficha_15MV"] < 1.25


def test_f87_hdr_co60_muro_oeste_insuficiente():
    T = F87.tvl_materiales(BD, F.densidades(BD))
    H = F87.hdr_co60(T)
    assert not H["caras"]["oeste_cuarto_caliente"]["cumple"]
    assert H["caras"]["techo_sanitarios_publicos"]["cumple"]


# ---------------------------------------------------------------- F88 (recálculo por densidad de tabique)
import blindaje_zumaya_f88 as F88


@pytest.mark.skipif(not any(F.LOSA.glob("res_ORD_250_s*.txt")), reason="sin corridas losa_tvl ORD_250")
def test_f88_ciclotron_25_menor_que_IBA_y_laberinto_despreciable():
    R = F88.ciclotron_25(F.ciclotron(BD))
    for k in ("oeste", "este", "sur_tapon", "techo"):
        assert R[k]["modulos_13cm"] < R[k]["IBA_GAMMA_cm"]
    assert R["laberinto"]["H_puerta_uSv_h"] < 0.01
    assert R["laberinto"]["suma_muros_en_serie_m"] * 100 >= R["laberinto"]["requerido_en_serie_25_cm"]


def test_f88_mn_conversion_real_mayor_que_nominal():
    T = F87.tvl_materiales(BD, F.densidades(BD))
    M = F88.mn_pet(BD, T)
    f = M["pet_ct"]["caras"]["norte_puerta"]
    assert f["TD-500"]["cm"] > f["GAMMA_nominal"]["5.0"]       # GAMMA usó densidad nominal


# ---------------------------------------------------------------- F89 (MC IBA, geotecnia, cargas)
import blindaje_zumaya_f89 as F89


def test_f89_td250_peso_de_pieza_coherente_con_nominal():
    t = BD["fichas_CONTUPLEX"]["TD-250"]
    assert abs(t["rho_por_peso_de_pieza"] - t["rho_nominal"]) < 0.05
    assert "ESTIMADAS" in t["origen_TVL"]


def test_f89_bunkeres_no_caben_en_cimentacion_superficial():
    C = F89.ciclotron()
    assert not C["cimentacion"]["superficial_viable"]
    assert C["cimentacion"]["pilas_D100_minimo_por_capacidad"] >= 3
    L = F89.linac(104, {"primaria_oeste": 117, "primaria_este": 104, "secundaria_norte": 78})
    assert L["cimentacion"]["presion_media_t_m2"] > 2 * max(BD["geotecnia"]["qa_superficial_t_m2"][k] for k in ("SM-1", "SM-2"))


def test_f89_tabiques_delgados_en_entrepiso_son_inestables_en_seco():
    E = F89.tabiques_entrepiso(4.0)
    assert all(v["estabilidad_junta_seca"]["vuelco_c030"] == "RIESGO" for v in E.values())


@pytest.mark.skipif(not F89.MC.exists(), reason="sin resultado del MC IBA")
def test_f89_mc_iba_espesores_menores_que_IBA():
    M = F89.mc_ciclotron()
    for k in ("este", "sur", "techo"):
        c = M["caras"][k]
        assert c["exterior_0_30cm_uSv_h"] < 0.01 * c["objetivo_uSv_h"]          # IBA sobrado ≥ 2 décadas
        assert c["modulo_13cm_directo"] < c["espesor_IBA_cm"]
