#!/usr/bin/env python3
"""F88 — Recálculo por densidad de tabique (adenda append-only a F86/F87), a petición del usuario (31-10-2026):
  1. Ciclotrón con TABIQUE 2.5 g/cm³ en todos los muros, incluido el laberinto (MC Geant4 losa_tvl ORD_250 de F86 +
     estimación de laberinto por fórmula de Tesch, NCRP 144).
  2. Linac Versa HD con TD-550 en todas las caras (15 MV, NCRP 151; ficha y densidad real estimada).
  3. HDR Flexitron Co-60 con TD-350/400/500/550 (ficha y real).
  4. Yodo, cuartos calientes PET y MN, cuartos de inyección, PET/CT: espesores GAMMA a 2.35 convertidos a cada tabique
     por espesor másico con la densidad REAL (fotones ≥ 364 keV: región Compton). GAMMA convirtió con densidad nominal.
  5. Tomógrafo simulador (CT): NCRP 147 (no está en el PDF de GAMMA) con carga supuesta declarada.
Reglas: simulacion_teorica, pq no_declarada_nunca, append-only, pendiente_fuente nunca inventado; supuestos [EST].
"""
import datetime, json, math, os, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import blindaje_zumaya_f86 as F86
import blindaje_zumaya_f87 as F87

EV = F86.EV
OUT = EV / "fase88"
TAB = 13.0
TDS = ("TD-350", "TD-400", "TD-500", "TD-550")


def mod(t):
    return TAB * math.ceil(t / TAB - 1e-9) if t > 0 else 0.0


# ------------------------------------------------------------------ 1. ciclotrón con tabique 2.5
def ciclotron_25(C):
    """C = salida de F86.ciclotron(). Requeridos en hormigón 2.35 a partir del exterior MC de F85 (0.0403 µSv/h a 211 cm,
    300 µA) y conversión al material ORD_250 con los ajustes MC. Corrección por bóveda IBA más pequeña (4.0 × 3.9 m frente a
    5.9 × 4.7 m del modelo): factor (2.7/2.0)² en la dosis interior → +TVL·log10(1.82)."""
    H211, TVL235 = 0.0403, 26.0
    a0, b0 = C["ORD_235"]["ajuste"]["a"], C["ORD_235"]["ajuste"]["b"]
    a1, b1 = C["ORD_250"]["ajuste"]["a"], C["ORD_250"]["ajuste"]["b"]
    tvl25 = C["ORD_250"]["TVL_cm"]
    corr = tvl25 * math.log10((2.7 / 2.0) ** 2)
    horas = 2000.0

    def t25(obj_uSv_h):
        t235 = 211 - TVL235 * math.log10(obj_uSv_h / H211)
        return (a0 + b0 * t235 - a1) / b1 + corr

    caras = {   # cara: (colindancia, T, criterio)
        "oeste": ("exterior del predio / circulación perimetral", 1 / 5, "publico"),
        "este": ("radiofarmacia (personal ocupacionalmente expuesto)", 1.0, "controlada"),
        "sur_tapon": ("área verde (jardín)", 1 / 40, "publico"),
        "norte_laberinto": ("sala de control / cooling unit tras el laberinto", 1.0, "publico"),
        "techo": ("azotea (control de aire acondicionado, acceso restringido)", 1 / 40, "publico"),
    }
    IBA = {"oeste": 240, "este": 220, "sur_tapon": 250, "norte_laberinto": None, "techo": 230}
    res = {}
    for k, (col, T, crit) in caras.items():
        P_a = 1.0 if crit == "publico" else 5.0                  # mSv/año (público; controlada: restricción 5 mSv/año)
        obj = P_a * 1e3 / (horas * T)                            # µSv/h promedio con haz
        obj03 = (0.3 if crit == "publico" else 2.0) * 1e3 / (horas * T)
        r = dict(colindancia=col, T=T, criterio=crit, objetivo_uSv_h=round(obj, 2), objetivo_restriccion_uSv_h=round(obj03, 2),
                 requerido_25_cm=round(t25(obj), 0), requerido_25_restriccion_cm=round(t25(obj03), 0),
                 IBA_GAMMA_cm=IBA[k])
        r["modulos_13cm"] = mod(r["requerido_25_restriccion_cm"])
        if IBA[k]:
            r["ahorro_vs_IBA_cm"] = IBA[k] - r["modulos_13cm"]
        res[k] = r
    # laberinto: Tesch (NCRP 144) — geometría medida en el plano IBA del PDF GAMMA (68 px/m): bóveda 4.0×3.9 m, sección
    # de pasillo ≈ 1.1 × 2.5 m, 1 tramo corto (1.5 m) + 4 tramos largos (~6.0 m) + tramo final (1.3 m)
    A = 1.1 * 2.5
    def f(d):
        return math.exp(-d / 0.45) + 0.022 * A ** 1.3 * math.exp(-d / 2.35)
    H_int = 1.0e7 * (300 / 180) * (2.7 / 2.0) ** 2            # µSv/h en la boca del laberinto [EST, conservador]
    tramos = [1.5, 6.0, 6.0, 6.0, 6.0, 1.3]
    H = H_int
    for d in tramos:
        H *= f(d)
    sum_muros = 0.40 + 0.60 + 0.59 + 0.93                     # espesores rotulados del laberinto (m)
    res["laberinto"] = dict(metodo="Tesch (NCRP 144) por tramo, d en m por eje del pasillo", A_m2=A, tramos_m=tramos,
                            H_boca_uSv_h=round(H_int), H_puerta_uSv_h=float(f"{H:.2g}"),
                            muros_rotulados_m=[0.40, 0.60, 0.59, 0.93], suma_muros_en_serie_m=round(sum_muros, 2),
                            requerido_en_serie_25_cm=res["norte_laberinto"]["requerido_25_restriccion_cm"],
                            nota=("el streaming por el laberinto de 5 tramos es despreciable; lo que manda es la penetración "
                                  "directa a través de los muros del laberinto en serie (≈ 2.5 m rotulados + macizos entre "
                                  "pasillos): con tabique 2.5 basta que la suma en la línea recta bóveda→exterior sea ≥ el "
                                  "requerido del muro norte; cada muro individual puede quedar en 0.39–0.65 m"))
    res["material"] = dict(TVL_cm=tvl25, TVL_g_cm2=C["ORD_250"]["TVL_g_cm2"], composicion="concreto ordinario 2.5 (H ≈ 1 %) [EST: la ficha del tabique 2.5 no se ha entregado]",
                           correccion_boveda_cm=round(corr, 1))
    return res


# ------------------------------------------------------------------ 2. linac con TD-550 en todas las caras
def linac_td550(T):
    W, P = 900.0, 0.02e-3
    iso = (41.025, 49.125)
    caras = {  # cara: (d m, U, T, tipo, DWG cm, GAMMA 5.5 calc, colindancia)
        "primaria_oeste": (5.46, 0.25, 1 / 5, "pri", 65, 63.1, "equipos / IDF / circulación (T=1/5)"),
        "primaria_este": (5.46, 0.25, 1 / 20, "pri", 65, 62.48, "baños públicos / fachada (T=1/20)"),
        "losa": (3.46, 0.25, 1.0, "pri", 100, 95.72, "sala de espera N1 (T=1)"),
        "secundaria_norte": (52.82 - iso[1] + 0.3, 1.0, 1.0, "fuga", 39, 37.86, "sanitarios/vestíbulo (T=1)"),
        "secundarias_laterales_fuera_franja": (45.19 - iso[0] + 0.3, 1.0, 1 / 5, "fuga", 40, 37.48, "laterales fuera de la franja primaria"),
        "laberinto_int+ext": (iso[1] - 42.36 + 0.3, 1.0, 1.0, "fuga", 30 + 26, 20 + 20, "sala de control al sur, a través de ambos muros del laberinto"),
    }
    out = {}
    for k, (d, U, Tt, tipo, dwg, gam, col) in caras.items():
        B = P * d * d / (W * U * Tt) if tipo == "pri" else P * d * d / (1e-3 * W * Tt)
        n = -math.log10(B)
        kk = "primaria" if tipo == "pri" else "fuga"
        tf, tr = T["TD-550"][f"{kk}_ficha"]["15MV"], T["TD-550"][f"{kk}_real"]["15MV"]
        out[k] = dict(colindancia=col, d_m=round(d, 2), T=Tt, n_TVL=round(n, 2), DWG_cm=dwg, GAMMA_55_calc_cm=gam,
                      TD550_ficha_cm=round(n * tf, 1), TD550_ficha_mod=mod(n * tf), TD550_real_cm=round(n * tr, 1), TD550_real_mod=mod(n * tr),
                      TD550_6MV_ficha_cm=round(n * T["TD-550"][f"{kk}_ficha"]["6MV"], 1))
    return {"energia": "15 MV (Versa HD); 6 MV de referencia", "W_Gy_sem": W, "caras": out,
            "pendiente": "puerta y laberinto a 15 MV: fotoneutrones + gammas de captura (NCRP 151 §2.4) — requiere geometría de puerta"}


# ------------------------------------------------------------------ 3. HDR Co-60 por tabique
def hdr_por_tabique(T):
    H = F87.hdr_co60(T)
    tv_c = 21.8
    out = {}
    for k, c in H["caras"].items():
        if c["material"] == "hormigon":
            out[k] = dict(DWG=f"{c['DWG_cm']} cm hormigón 2.35", requerido_hormigon_cm=c["requerido_cm"]); continue
        n = c[c["criterio"]]["n"]
        fila = dict(criterio=c["criterio"], n_TVL=n, DWG_cm_TD350=c["DWG_cm"], hormigon_235_cm=round(n * tv_c, 1))
        for m in TDS:
            for base in ("rho_nominal", "rho_real"):
                t = n * tv_c * 2.35 / T[m][base]
                fila[f"{m}|{'ficha' if base == 'rho_nominal' else 'real'}"] = dict(cm=round(t, 1), mod=mod(t))
        out[k] = fila
    return {"W_mGy_sem_1m": H["W_mGy_sem_1m"], "supuesto_actividad_GBq": 74.0, "caras": out}


# ------------------------------------------------------------------ 4. medicina nuclear / PET por conversión másica
def mn_pet(bd, T):
    G = bd["estimaciones_GAMMA"]
    salas = {"pet_ct": ("PET/CT", 511), "inyeccion_pet_1_2": ("inyección PET 1–2", 511), "inyeccion_pet_3_4": ("inyección PET 3–4", 511),
             "cuarto_caliente_pet": ("cuarto caliente PET", 511), "yodo": ("cuarto de yodo (I-131)", 364),
             "inyeccion_mn_esfuerzo": ("inyección MN / esfuerzo", 140), "cuarto_caliente_mn": ("cuarto caliente MN", 364)}
    out = {}
    for s, (nombre, keV) in salas.items():
        g = G[s]; fil = {}
        src = g.get("calc_cm_2.35_3.5_5.0") or g.get("calc_cm_2.35_3.5") or g.get("concreto_cm_2.35_3.5") or {}
        extra = {}
        if "techo_cm" in g: extra["techo"] = g["techo_cm"]
        if "piso_cm" in g: extra["piso"] = g["piso_cm"]
        if "techo_cm_2.35" in g: extra["techo"] = [g["techo_cm_2.35"]]
        if "piso_cm_2.35" in g: extra["piso"] = [g["piso_cm_2.35"]]
        for cara, vals in list(src.items()) + list(extra.items()):
            t235 = vals[0] if isinstance(vals, list) else vals
            if t235 is None: continue
            f = dict(GAMMA_235_cm=t235, GAMMA_nominal={"3.5": vals[1] if isinstance(vals, list) and len(vals) > 1 else None,
                                                        "5.0": vals[2] if isinstance(vals, list) and len(vals) > 2 else None})
            for m in TDS:
                t = t235 * 2.35 / T[m]["rho_real"]
                f[m] = dict(cm=round(t, 1), mod=mod(t))
            fil[cara] = f
        out[s] = dict(sala=nombre, energia_keV=keV, caras=fil, plomo_GAMMA={k: v for k, v in g.items() if "Pb" in k},
                      nota=("140 keV: el tabique alto-Z (Ba) rinde mejor que el escalado másico → conversión conservadora" if keV < 300
                            else "Compton dominante → escalado másico con densidad real"))
    return out


# ------------------------------------------------------------------ 5. tomógrafo simulador (NCRP 147)
def ct_simulador(T):
    # [EST] carga: 25 pac/día × 5 d = 125/sem; DLP 1000 mGy·cm (simulación de cuerpo, barrido largo); κ cuerpo 3e-4 cm⁻¹ ×1.2
    N, DLP, kap = 125, 1000.0, 3e-4
    K1 = N * kap * DLP * 1.2                                   # mGy/sem a 1 m (dispersión)
    a, b, g = 0.0336, 0.0122, 0.519                            # NCRP 147 Tabla A.1, hormigón, CT 140 kVp [mm⁻¹]
    aP, bP, gP = 2.009, 3.99, 0.342                            # plomo, CT 140 kVp
    def x_arch(B, a, b, g):
        return (1 / (a * g)) * math.log((B ** (-g) + b / a) / (1 + b / a))
    caras = {"control (controlada)": (3.0, 1.0, 0.1), "pasillo (público, T=1/5)": (3.0, 1 / 5, 0.02),
             "sala contigua (público, T=1)": (3.0, 1.0, 0.02), "techo N2 (público, T=1)": (4.9, 1.0, 0.02),
             "piso N0 (público, T=1)": (4.7, 1.0, 0.02)}
    out = {}
    for k, (d, Tt, P) in caras.items():
        B = P * d * d / (K1 * Tt)
        if B >= 1:
            out[k] = dict(B=round(B, 3), requerido="no requiere"); continue
        xc = x_arch(B, a, b, g) / 10.0                        # cm hormigón
        xp = x_arch(B, aP, bP, gP)                             # mm Pb
        f = dict(B=float(f"{B:.3g}"), hormigon_235_cm=round(xc, 1), plomo_mm=round(xp, 2))
        for m in TDS:
            t = xc * 2.35 / T[m]["rho_real"]
            f[m] = dict(cm=round(t, 1), mod=mod(t))
        out[k] = f
    return {"supuestos_EST": dict(pacientes_sem=N, DLP_mGy_cm=DLP, kappa_cm=kap, kVp=140), "K1_mGy_sem_1m": round(K1, 1), "caras": out,
            "nota": "a ~60–70 keV efectivos el Ba del tabique aumenta mucho la atenuación por masa: la conversión másica es conservadora; DWG anota 13–26 cm a 5 g/cm³"}


def ejecutar():
    OUT.mkdir(parents=True, exist_ok=True)
    bd = json.load(open(F86.BD)); dens = F86.densidades(bd)
    T = F87.tvl_materiales(bd, dens)
    C = F86.ciclotron(bd)
    out = {"fase": 88, "version": "3.14.0", "tipo": "simulacion_teorica", "pq": "no_declarada_nunca",
           "fecha": datetime.datetime.now().isoformat(timespec="seconds"), "md5_bd": F86.md5(F86.BD),
           "ciclotron_tabique_25": ciclotron_25(C), "linac_TD550": linac_td550(T), "hdr_co60_por_tabique": hdr_por_tabique(T),
           "mn_pet_por_tabique": mn_pet(bd, T), "ct_simulador": ct_simulador(T),
           "densidades_reales": {m: T[m]["rho_real"] for m in TDS}}
    json.dump(out, open(OUT / "blindaje_zumaya_f88.json", "w"), indent=1, ensure_ascii=False, default=float)
    return out


if __name__ == "__main__":
    o = ejecutar()
    print(json.dumps(o["ciclotron_tabique_25"], indent=0, ensure_ascii=False)[:3000])
    for k, v in o["linac_TD550"]["caras"].items(): print(k, v)
    for k, v in o["hdr_co60_por_tabique"]["caras"].items(): print(k, v)
    for s, v in o["mn_pet_por_tabique"].items():
        print("==", v["sala"], v["energia_keV"])
        for c, f in v["caras"].items(): print("  ", c, f["GAMMA_235_cm"], f["GAMMA_nominal"], {m: f[m]["mod"] for m in TDS}, {m: f[m]["cm"] for m in TDS})
    print(o["ct_simulador"])
