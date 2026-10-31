#!/usr/bin/env python3
"""F87 — Adenda append-only a F86: fichas técnicas CONTUPLEX (TD-350/400/500/550) y equipos confirmados por el usuario
(Elekta Versa HD 6/10/15 MV; Flexitron con Co-60; Leksell Gamma Knife Co-60).

1. Fichas: TVL del proveedor por energía (primaria y fuga). Trazabilidad: solo TD-350 está MEDIDO (6 y 10 MV); TD-400/500/
   550 se obtuvieron ESCALANDO por densidad NOMINAL. Con la densidad volumétrica real del IMCYC (F86: "5" → 3.99), la
   TVL física se obtiene escalando la medición TD-350 con densidades REALES: TVL_X = TVL_350 · ρ350_real / ρX_real.
2. Linac Versa HD diseñado a 15 MV (peor caso de las tres energías), NCRP 151, convención de TVL única del proveedor.
3. Braquiterapia HDR Flexitron Co-60 (reemplaza la hipótesis Ir-192 de F86), SRS-47.
Reglas: simulacion_teorica, pq no_declarada_nunca, append-only, pendiente_fuente nunca inventado.
"""
import datetime, json, math, os, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import blindaje_zumaya_f86 as F86

RAIZ = F86.RAIZ
EV = F86.EV
OUT = EV / "fase87"
TAB = 13.0


def mod(t):
    return TAB * math.ceil(t / TAB - 1e-9)


def tvl_materiales(bd, dens):
    fx = bd["fichas_CONTUPLEX"]
    r350 = dens["tabique_NIPOL_3.5"]["seca"]
    real = {"TD-350": r350, "TD-400": dens["tabique_NIPOL_4"]["seca"], "TD-500": dens["tabique_NIPOL_5"]["seca"],
            "TD-550": round(5.5 * dens["tabique_NIPOL_5"]["seca_sobre_aparente"], 2)}       # TD-550: estimada (sin informe)
    T = {}
    for m in ("TD-350", "TD-400", "TD-500", "TD-550"):
        T[m] = {"rho_nominal": fx[m]["rho_nominal"], "rho_real": real[m],
                "rho_real_origen": "IMCYC OT-521 (seca)" if m != "TD-550" else "estimada 5,5×(seca/aparente del '5') — pendiente_fuente",
                "primaria_ficha": fx[m]["TVL_primaria_cm"], "fuga_ficha": fx[m]["TVL_fuga_cm"],
                "primaria_real": {e: round(v * r350 / real[m], 1) for e, v in fx["TD-350"]["TVL_primaria_cm"].items()},
                "fuga_real": {e: round(v * r350 / real[m], 1) for e, v in fx["TD-350"]["TVL_fuga_cm"].items()}}
        T[m]["factor_real_sobre_ficha_15MV"] = round(T[m]["primaria_real"]["15MV"] / fx[m]["TVL_primaria_cm"]["15MV"], 3)
    # coherencia física de la medición TD-350 con NCRP 151 por espesor másico
    T["chequeo_masico_TD350"] = {e: dict(TD350_g_cm2=round(v * r350, 1), hormigon_TVLe_g_cm2=round(F86.TVL_PRI[e][1] * 2.35, 1))
                                 for e, v in fx["TD-350"]["TVL_primaria_cm"].items() if e in F86.TVL_PRI}
    return T


def linac(T):
    W, P = 900.0, 0.02e-3
    caras = {"primaria_lateral_T1": (5.46, 0.25, 1.0, "pri"), "primaria_lateral_T1_20_banos": (5.46, 0.25, 1 / 20, "pri"),
             "losa_sala_espera_T1": (3.46, 0.25, 1.0, "pri"), "losa_area_verde_T1_40": (3.46, 0.25, 1 / 40, "pri"),
             "secundaria_norte_fuga_T1": (3.99, 1.0, 1.0, "fuga")}
    DWG = {"primaria_lateral_T1": 65, "primaria_lateral_T1_20_banos": 65, "losa_sala_espera_T1": 100,
           "losa_area_verde_T1_40": 100, "secundaria_norte_fuga_T1": 39}
    out = {}
    for k, (d, U, Tt, tipo) in caras.items():
        B = P * d * d / (W * U * Tt) if tipo == "pri" else P * d * d / (1e-3 * W * Tt)
        n = -math.log10(B)
        fila = {"n_TVL": round(n, 2), "DWG_cm": DWG[k]}
        tv = F86.TVL_PRI["15MV"] if tipo == "pri" else F86.TVL_FUGA["15MV"]
        fila["hormigon_235_cm"] = round(tv[0] + (n - 1) * tv[1], 1)
        for m in ("TD-500", "TD-550"):
            kk = "primaria" if tipo == "pri" else "fuga"
            tf, tr = T[m][f"{kk}_ficha"]["15MV"], T[m][f"{kk}_real"]["15MV"]
            fila[m] = {"ficha_cm": round(n * tf, 1), "ficha_modulos_cm": mod(n * tf), "real_cm": round(n * tr, 1),
                       "real_modulos_cm": mod(n * tr), "DWG_transmision_real_vs_P": round(10 ** (n - DWG[k] / tr), 1)}
        fila["TD-500_6MV_ficha_cm"] = round(n * (T["TD-500"]["primaria_ficha" if tipo == "pri" else "fuga_ficha"]["6MV"]), 1)
        out[k] = fila
    return {"W_Gy_sem": W, "energia_diseno": "15 MV (Versa HD 6/10/15)", "caras": out,
            "neutrones": "15 MV: fotoneutrones relevantes en laberinto/puerta; TD de bajo hidrógeno no modera — puerta con BPE/Pb y laberinto a evaluar (NCRP 151 §2.4, método de Kersey/Wu-McGinley) — pendiente"}


def hdr_co60(T):
    A, G = 74.0, 0.306                                     # GBq (2 Ci, supuesto), mGy·m²/(GBq·h)
    t_h = 50 * 25 / 60
    W = A * G * t_h                                        # mGy/sem a 1 m
    tv_c = 21.8
    tv_ficha = tv_c * 2.35 / 3.5
    tv_real = tv_c * 2.35 / T["TD-350"]["rho_real"]
    src = (24.2, 37.4)
    caras = {"oeste_cuarto_caliente": (src[0] - 21.89 + 0.3, 39, 1.0, True, "TD-350"),
             "norte_pasillo": (40.71 - src[1] + 0.3, 52, 1.0, False, "TD-350"),
             "sur_fachada": (src[1] - 34.20 + 0.3, 39, 1 / 40, False, "TD-350"),
             "este_control_tabique+muro": (28.87 - src[0] + 0.3, 39, 1.0, True, "TD-350"),
             "techo_sanitarios_publicos": (5.40 - 1.0 + 0.3, 39, 1 / 20, False, "TD-350"),
             "piso_gamma_knife": (1.0 + 3.70, 70, 1.0, True, "hormigon")}
    out = {}
    for k, (d, prov, Tt, ctrl, mat) in caras.items():
        fila = {"d_m": round(d, 2), "DWG_cm": prov, "material": mat, "T": Tt, "controlada": ctrl}
        for nP, P in (("publico", 0.02), ("controlada", 0.1)):
            for nT, TT in (("T1", 1.0), ("Treal", Tt)):
                n = max(0.0, -math.log10(P * d * d / (W * TT)))
                if mat == "hormigon":
                    fila[f"{nP}|{nT}"] = {"n": round(n, 2), "cm": round(n * tv_c, 1)}
                else:
                    fila[f"{nP}|{nT}"] = {"n": round(n, 2), "cm_ficha": round(n * tv_ficha, 1), "cm_real": round(n * tv_real, 1)}
        # holgura del espesor dibujado con el criterio aplicable (controlada si lo es; público con T real si no)
        clave = "controlada|T1" if ctrl else "publico|Treal"
        req = fila[clave]["cm"] if mat == "hormigon" else fila[clave]["cm_real"]
        fila["criterio"] = clave; fila["requerido_cm"] = req; fila["cumple"] = prov >= req
        out[k] = fila
    return {"W_mGy_sem_1m": round(W, 1), "actividad_GBq": A, "TVL_cm": {"hormigon_235": tv_c, "TD350_ficha": round(tv_ficha, 1), "TD350_real": round(tv_real, 1)},
            "caras": out, "nota": "Co-60 (1,25 MeV): región Compton → escalado másico fiable; la ficha CONTUPLEX no da TVL para Co-60"}


def ejecutar():
    OUT.mkdir(parents=True, exist_ok=True)
    bd = json.load(open(F86.BD)); dens = F86.densidades(bd)
    T = tvl_materiales(bd, dens)
    out = {"fase": 87, "version": "3.13.0", "tipo": "simulacion_teorica", "pq": "no_declarada_nunca",
           "fecha": datetime.datetime.now().isoformat(timespec="seconds"), "md5_bd": F86.md5(F86.BD),
           "materiales": T, "linac": linac(T), "hdr_co60": hdr_co60(T),
           "ciclotron": "sin cambio frente a F86: la ficha confirma matriz Fe+Ba+Ca, dentro de las dos hipótesis simuladas (magnetita/barita) → concreto ordinario 2,35–2,5",
           "advertencias": ["TVL de TD-400/500/550 escaladas por densidad nominal; IMCYC midió '5' = 3,99 g/cm³ (la propia ficha TD-500 declara 2,66–2,68 de obra)",
                            "inconsistencias de ficha registradas en la BD (TVL 13,6/18,6/20,4 cm para TD-550; densidad 5,00 en TD-550)",
                            "actividad de la fuente Co-60 del Flexitron supuesta 74 GBq (pendiente_fuente)",
                            "U(k=2) ≈ 25 % en las TVL del proveedor no está incluida en los espesores"]}
    json.dump(out, open(OUT / "blindaje_zumaya_f87.json", "w"), indent=1, ensure_ascii=False, default=float)
    with open(OUT / "registro_materiales.jsonl", "a") as f:
        for m in ("TD-400", "TD-500", "TD-550"):
            f.write(json.dumps({"fecha": out["fecha"], "material": m, "supuesto_previo": "TVL de ficha (densidad nominal)",
                                "valor_corregido_15MV_cm": T[m]["primaria_real"]["15MV"], "estado": "discrepancia_cuantificada"}, ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":
    o = ejecutar()
    for m, v in o["materiales"].items():
        print(m, {k: v[k] for k in v if k in ("rho_real", "factor_real_sobre_ficha_15MV")} if "rho_real" in v else v)
    for k, v in o["linac"]["caras"].items():
        print(k, v)
    print(o["hdr_co60"]["W_mGy_sem_1m"], o["hdr_co60"]["TVL_cm"])
    for k, v in o["hdr_co60"]["caras"].items():
        print(k, v["d_m"], v["DWG_cm"], v["criterio"], v["requerido_cm"], v["cumple"], v["publico|T1"])
