#!/usr/bin/env python3
"""F89 — (1) MC Geant4 del búnker del ciclotrón con la geometría IBA (tabique 2,5 = concreto estándar, 300 µA en un blanco,
área verde vacía sobre el techo) y (2) bajada de cargas PRELIMINAR de los blindajes para el análisis estructural.

Reglas: simulacion_teorica / predimensionamiento; NO sustituye el diseño de un Corresponsable en Seguridad Estructural (CSE).
Todo dato no entregado se marca pendiente_fuente; los supuestos se listan explícitamente en `supuestos`.
Unidades: t (tonelada fuerza ≈ 9,81 kN), m.
"""
import datetime, json, math, os, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import blindaje_zumaya_f86 as F86

EV = F86.EV
OUT = EV / "fase89"
MC = pathlib.Path(os.environ.get("ZUMAYA_MC_IBA", pathlib.Path(__file__).resolve().parents[2] / "mc_ciclotron/resultado_iba.json"))
TAB = 13.0
G_CONC, G_RC = 2.40, 2.40          # t/m³: concreto simple / reforzado
SUP = {
    "rho_tabique_25": (2.50, "usuario: tabique 2,5 = concreto alta densidad estándar; peso volumétrico de muro 2,5 t/m³"),
    "rho_TD350": (3.32, "IMCYC densidad seca (no nominal)"), "rho_TD500": (3.99, "IMCYC densidad seca"),
    "rho_TD550": (4.29, "estimada (5,5 × seca/aparente) — pendiente_fuente; pesar piezas en obra"),
    "techo_verde_kg_m2": (600, "jardín ligero 30 cm sustrato saturado + impermeabilización (supuesto)"),
    "viva_azotea_kg_m2": (100, "NTC-CyA CDMX 2023 azotea pend. <5 % (referencia, la norma local puede variar)"),
    "viva_hospital_kg_m2": (350, "salas de espera / circulaciones hospital (referencia NTC-CyA)"),
    "h_entrepiso_m": (4.00, "altura de entrepiso genérica en niveles N2–N4 — pendiente_fuente (cortes)"),
    "q_adm_t_m2": ((4.9, 5.5), "geotecnia OD 2025: B=1 m, Df=3.6 m (SM-2 / SM-1)"),
    "Q_pila_t": (247.6, "geotecnia OD 2025: pila Ø1.00 m L=21 m, Qadm neta SM-2 (gobierna); ×1.2 en sismo"),
    "s_pila_cm": (4.45, "asentamiento elástico pila Ø1.00 a carga admisible (SM-2)"),
    "c_sismico": ((0.15, 0.30), "rango de revisión; geotecnia: zona B, terreno II, grupo A ×1.5 — espectro de diseño del CSE pendiente"),
    "mu_seco": (0.6, "fricción tabique-tabique en junta seca (valor típico; ensayar)"),
    "peso_ciclotron": (18.0, "IBA SRG MID_55672 Rev G tabla 4: 18 000 kg sobre 4 apoyos 220×220 mm (10 kg/cm²); nivel bajo patas ±1 mm"),
    "peso_linac": (8.0, "Versa HD gantry + base, orden de magnitud — pendiente_fuente (site planning Elekta)"),
    "peso_gamma_knife": (None, "peso del Leksell Gamma Knife y huella — pendiente_fuente (site planning Elekta; orden de 20 t)"),
}


def cimentacion(nombre, W_t, huella_m2, junta):
    """compara presión media con qa superficial y estima pilas Ø1.00 (L 21 m) por capacidad; sin sismo ni efecto de grupo."""
    qa = SUP["q_adm_t_m2"][0]; Q = SUP["Q_pila_t"][0]
    p = W_t / huella_m2
    n = math.ceil(W_t / Q)
    return {"elemento": nombre, "W_t": round(W_t), "huella_m2": round(huella_m2, 1), "presion_media_t_m2": round(p, 1),
            "qa_superficial_t_m2": list(qa), "superficial_viable": p <= min(qa),
            "pilas_D100_minimo_por_capacidad": n, "pilas_sugeridas": max(n + 2, 4),
            "asentamiento_pila_cm": SUP["s_pila_cm"][0], "junta_constructiva": junta,
            "riesgo": ("asentamiento diferencial contra el edificio contiguo: con junta, controlable; sin junta, las pilas del búnker deben "
                       "dimensionarse para igualar asentamientos con las columnas vecinas (o transferir con contratrabes rígidas)")}


def mod(t):
    return TAB * math.ceil(t / TAB - 1e-9)


def losa(q_t_m2, L, apoyo="simple"):
    """momento y cortante por metro de ancho; peralte efectivo orientativo L/d≈10-12 para cargas tan altas."""
    c = 8.0 if apoyo == "simple" else 10.0
    return {"q_t_m2": round(q_t_m2, 2), "L_m": L, "M_t_m_por_m": round(q_t_m2 * L * L / c, 1), "V_t_por_m": round(q_t_m2 * L / 2, 1),
            "reaccion_muro_t_m": round(q_t_m2 * L / 2, 1)}


def muro(t_m, h_m, rho, reaccion=0.0):
    w = t_m * h_m * rho
    return {"espesor_m": t_m, "altura_m": h_m, "rho": rho, "peso_propio_t_m": round(w, 1), "reaccion_losa_t_m": reaccion,
            "total_t_m": round(w + reaccion, 1), "presion_base_t_m2_sin_zapata": round((w + reaccion) / t_m, 1),
            "esbeltez_t_h": round(t_m / h_m, 3)}


def estabilidad_seca(t_m, h_m):
    """bloque rígido en junta seca: vuelca si c > t/h (sin conexión superior); desliza si c > μ."""
    cmin, cmax = SUP["c_sismico"][0]
    mu = SUP["mu_seco"][0]
    r = t_m / h_m
    return {"t_sobre_h": round(r, 3), "vuelco_c015": "seguro" if r > cmin else "RIESGO", "vuelco_c030": "seguro" if r > cmax else "RIESGO",
            "deslizamiento": "seguro" if mu > cmax else "RIESGO",
            "nota": "muro libre sin liga a la estructura; con dalas/castillos o anclaje a losa el modo cambia a flexión fuera del plano"}


def ciclotron(espesores_cm=None):
    """bóveda IBA 4,00 × 3,94 × 2,50 m (interior). espesores por cara: F88 (módulos 13 cm, tabique 2,5) o MC F89."""
    e = espesores_cm or {"este": 182, "oeste": 182, "sur": 156, "techo": 156, "norte_laberinto_suma": 195}
    rho = SUP["rho_tabique_25"][0]
    tt = e["techo"] / 100
    # techo: losa estructural de concreto reforzado + tabique 2,5 apilado encima hasta completar el espesor de blindaje
    q = tt * rho + SUP["techo_verde_kg_m2"][0] / 1000 + SUP["viva_azotea_kg_m2"][0] / 1000
    L = 4.00 + 2 * 0.15                                                          # claro a ejes de apoyo (≈ 15 cm de asiento)
    T = losa(q, L)
    T["peralte_sugerido_m"] = round(max(0.40, L / 10), 2)
    h_muro = 2.50 + tt
    caras = {k: muro(e[k] / 100, h_muro, rho, T["reaccion_muro_t_m"] if k in ("este", "oeste") else 0.0) for k in ("este", "oeste", "sur")}
    for k in caras:
        caras[k]["estabilidad_junta_seca"] = estabilidad_seca(e[k] / 100, h_muro)
    # peso total del búnker (huella exterior)
    Lx, Ly = 4.00 + (e["este"] + e["oeste"]) / 100, 3.94 + (e["sur"]) / 100 + 0.40
    P_techo = q * Lx * Ly
    P_muros = sum(caras[k]["peso_propio_t_m"] * (3.94 + 0.4 if k != "sur" else 4.00) for k in caras)
    lab = 9.22 * 3.2 * 0.5 * h_muro * rho                                        # laberinto: masa ≈ 50 % de su huella (pasillos huecos)
    total = P_techo + P_muros + lab + SUP["peso_ciclotron"][0] + 0.6 * G_RC * Lx * (Ly + 9.22)
    huella = Lx * (Ly + 9.22)
    return {"espesores_cm": e, "techo": T, "muros": caras, "peso_total_t": round(total, 0), "huella_m2": round(huella, 1),
            "presion_media_losa_cimentacion_t_m2": round(total / huella, 1),
            "cimentacion": cimentacion("búnker ciclotrón (losa 0.60 m incluida)", total, huella, True),
            "apoyos_ciclotron": "18 t en 4 apoyos de 220×220 mm (≈ 93 t/m² local): losa ≥ 0.60 m y la pila Ø1.00 dibujada bajo el centro; tolerancia de nivel ±1 mm ⇒ la losa del búnker y el ciclotrón deben quedar sobre el mismo grupo de pilas",
            "nota_cimentacion": "la presión media supera la qa superficial (4.9–5.5 t/m²) ⇒ pilas, como recomienda el estudio geotécnico. "
                                "El DWG ya separa el búnker con junta constructiva (correcto). Líneas de transferencia: IBA pide ductos a 0.50 m en losa; "
                                "la zanja cruza el muro este y la junta bajo la crujía contraventeada NA N1–N2 ⇒ coordinar paso bajo la contratrabe."}


def linac(techo_TD550_cm, muros_cm, h_int=3.30, L=7.50):
    rho = SUP["rho_TD550"][0]
    tt = techo_TD550_cm / 100
    q = tt * rho + SUP["techo_verde_kg_m2"][0] / 1000 + SUP["viva_azotea_kg_m2"][0] / 1000
    T = losa(q + 0.6 * G_RC, L)                                                  # + losa estructural de 60 cm que sostiene el tabique
    T["nota"] = "el tabique no trabaja como losa: se apila sobre una losa/trabes de concreto reforzado; claro de 7,5 m con 6–8 t/m² exige trabes peraltadas o losa postensada"
    caras = {k: muro(v / 100, h_int + 0.6 + tt, rho, T["reaccion_muro_t_m"] if k.startswith("primaria") else 0.0) for k, v in muros_cm.items()}
    for k in caras:
        caras[k]["estabilidad_junta_seca"] = estabilidad_seca(muros_cm[k] / 100, h_int + 0.6 + tt)
    # peso total con la geometría DWG PB: interior 7.51 × 9.81 m; perímetro medio por cara
    Li = {"primaria_oeste": 9.81, "primaria_este": 9.81, "secundaria_norte": 7.51 + 2 * 1.0, "sur_laberinto": 7.51 + 2 * 1.0}
    tw = dict(muros_cm); tw.setdefault("sur_laberinto", 65)
    W_muros = sum(tw[k] / 100 * (h_int + 0.6 + tt) * rho * Li[k] for k in Li) + 7.5 * 0.65 * h_int * rho
    W_techo = q * 7.51 * 9.81 + 0.6 * G_RC * (7.51 + 2) * (9.81 + 2)   # tabique sólo sobre el claro (sobre muros ya está en su altura)
    W_losa_cim = 0.6 * G_RC * (7.51 + 2.2) * (9.81 + 2.2)
    W = W_muros + W_techo + W_losa_cim + SUP.get("peso_linac", (8.0,))[0]
    huella = (7.51 + 2.2) * (9.81 + 2.2)
    return {"techo_TD550_cm": techo_TD550_cm, "techo": T, "muros": caras, "peso_total_t": round(W),
            "cimentacion": cimentacion("búnker linac (sin junta en el DWG)", W, huella, False),
            "masa_superficial_techo_t_m2": {"TD550_real": round(tt * rho, 2), "espesor_concreto_235_misma_masa_m": round(tt * rho / 2.35, 2),
                                            "lectura": "para fotones el blindaje depende de la masa por área: el techo pesa ≈ lo mismo en TD-550 que en concreto; la densidad solo ahorra espesor (y altura de edificio)"}}


def tabiques_entrepiso(h):
    """muros de blindaje sobre losas de entrepiso (cuartos calientes, inyección, PET-CT, HDR)."""
    filas = {"HDR_Co60_oeste_TD500": (0.39, 3.99), "HDR_Co60_norte_TD350": (0.52, 3.32), "PET_CT_TD500_52": (0.52, 3.99),
             "cuarto_caliente_PET_TD500_26": (0.26, 3.99), "inyeccion_TD350_26": (0.26, 3.32), "CT_simulador_TD350_13": (0.13, 3.32)}
    out = {}
    for k, (t, rho) in filas.items():
        m = muro(t, h, rho)
        m["estabilidad_junta_seca"] = estabilidad_seca(t, h)
        m["carga_lineal_vs_muro_divisorio_ligero"] = round(m["peso_propio_t_m"] / (0.15 * h * 1.5), 1)   # vs block hueco 15 cm (1,5 t/m³)
        out[k] = m
    return out


def mc_ciclotron():
    if not MC.exists():
        return {"estado": "pendiente: corridas en curso"}
    R = json.load(open(MC))
    return {"geometria": "bóveda 4.00×3.94×2.50 m, muros E 2.20 / O 2.40 / S 2.50 / techo 2.30 (IBA); DWG PB 31/10: 4.00×4.00",
            "fisica": "Geant4 11.4.3 QGSP_BIC_HP, espectro BON21 ¹⁸O(p,n) 4.93e-3 n/p, H*(10) ICRP-74, importancia planar f=3 por 10 cm",
            "corridas": R["corridas"], "caras": {k: {kk: v.get(kk) for kk in ("espesor_IBA_cm", "ajuste", "exterior_0_30cm_uSv_h", "exterior_se",
                                                                             "exterior_ajuste_uSv_h", "objetivo_uSv_h", "objetivo", "factor_parche",
                                                                             "espesor_requerido_cm", "modulo_13cm", "ahorro_vs_IBA_cm",
                                                                             "espesor_requerido_directo_cm", "modulo_13cm_directo")}
                                                for k, v in R["caras"].items()}}


def ejecutar():
    OUT.mkdir(parents=True, exist_ok=True)
    M = mc_ciclotron()
    e = None
    if "caras" in M:
        # recomendado = el mayor entre F88 (losa_tvl escalada), MC ajuste exponencial y MC método directo (parche 50×50)
        F88m = {"este": 182, "oeste": 182, "sur": 156, "techo": 156}
        e, M["recomendado"] = {}, {}
        for k in ("este", "oeste", "sur", "techo"):
            c = M["caras"].get(k, {})
            cand = {"F88": F88m[k], "MC_ajuste": c.get("modulo_13cm"), "MC_directo": c.get("modulo_13cm_directo")}
            e[k] = max(v for v in cand.values() if v)
            M["recomendado"][k] = dict(cand, recomendado_cm=e[k], IBA_cm=c.get("espesor_IBA_cm"),
                                       ahorro_cm=(c.get("espesor_IBA_cm") or 0) - e[k])
        e["norte_laberinto_suma"] = 195
    out = {"fase": 89, "version": "3.15.0", "tipo": "simulacion_teorica + predimensionamiento_estructural", "pq": "no_declarada_nunca",
           "fecha": datetime.datetime.now().isoformat(timespec="seconds"), "md5_bd": F86.md5(F86.BD),
           "mc_ciclotron": M,
           "estructural": {"ciclotron_F88": ciclotron(), "ciclotron_MC": ciclotron(e) if e else None,
                           "linac_area_verde_T1_40": linac(104, {"primaria_oeste": 117, "primaria_este": 104, "secundaria_norte": 78}),
                           "linac_sala_espera_T1": linac(143, {"primaria_oeste": 117, "primaria_este": 104, "secundaria_norte": 78}),
                           "muros_en_entrepiso": tabiques_entrepiso(SUP["h_entrepiso_m"][0])},
           "supuestos": {k: {"valor": v[0], "origen": v[1]} for k, v in SUP.items()},
           "responsiva": "Predimensionamiento para dimensionar el problema; el diseño estructural y su responsiva corresponden a un "
                         "Corresponsable en Seguridad Estructural con estudio de mecánica de suelos."}
    json.dump(out, open(OUT / "blindaje_zumaya_f89.json", "w"), indent=1, ensure_ascii=False, default=float)
    return out


if __name__ == "__main__":
    o = ejecutar()
    E = o["estructural"]
    for k in ("ciclotron_F88", "ciclotron_MC"):
        c = E[k]
        if c:
            print(k, c["espesores_cm"], "peso", c["peso_total_t"], c["cimentacion"])
            for kk, v in c["muros"].items():
                print("  ", kk, v["total_t_m"], v["estabilidad_junta_seca"]["vuelco_c030"])
    for k in ("linac_area_verde_T1_40", "linac_sala_espera_T1"):
        print(k, E[k]["techo"]["M_t_m_por_m"], E[k]["peso_total_t"], E[k]["cimentacion"])
    for k, v in E["muros_en_entrepiso"].items():
        print(k, v["peso_propio_t_m"], v["estabilidad_junta_seca"]["vuelco_c015"], v["estabilidad_junta_seca"]["vuelco_c030"], v["carga_lineal_vs_muro_divisorio_ligero"])
