#!/usr/bin/env python3
"""F86 — BD de blindaje Zumaya: ingesta de los informes IMCYC de tabiques NIPOL (OT-521), estimaciones GAMMA y DWG
BIND 28-10-26; reevaluación del linac con la densidad REAL del tabique "5" y elección del material del búnker del
ciclotrón (concreto 2.35/2.5 vs tabique "3.5") con transmisión Geant4 (losa_tvl, espectro 18O(p,n) BON21 de kiube).

Hallazgo de entrada: los informes IMCYC no traen composición química ni TVL; miden masa específica (NMX-C-263).
El valor nominal del tabique coincide con la masa específica APARENTE (fase sólida, sin poros); la que atenúa es la
volumétrica (seca/en servicio): "5" → 3.99, "4" → 3.68, "3.5" → 3.32 g/cm³.
Reglas: simulacion_teorica, pq no_declarada_nunca, append-only, 18.10, pendiente_fuente nunca inventado.
Rutas: RPOS_EVIDENCIA, KIUBE_RAIZ (out/losa_tvl con res_<MAT>_s*.txt).
"""
import datetime, glob, hashlib, json, math, os, pathlib
import numpy as np

RAIZ = pathlib.Path(__file__).resolve().parents[1]
BD = RAIZ / "data/blindaje_zumaya/bd_blindaje_zumaya.json"
KIUBE = pathlib.Path(os.environ.get("KIUBE_RAIZ", "/mnt/agents/work/kiube_v035/kiube"))
LOSA = KIUBE / "out/losa_tvl"
EV = pathlib.Path(os.environ.get("RPOS_EVIDENCIA", "/mnt/agents/work/evidencia_v072"))
OUT = EV / "fase86"
TAB = 13.0                                         # módulo de tabique [cm]


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def modulo(t):
    return TAB * math.ceil(t / TAB - 1e-9)


# ------------------------------------------------------------------ materiales
def densidades(bd):
    out = {}
    for k, m in bd["materiales"].items():
        if "mediciones" not in m:
            continue
        M = m["mediciones"]
        seca, ap = np.mean(M["masa_especifica_seca"]), np.mean(M["masa_especifica_aparente"])
        inm = np.mean(M["masa_especifica_inmersion"])
        nominal = float(k.split("_")[-1])
        out[k] = dict(nominal=nominal, seca=round(seca, 3), inmersion=round(inm, 3), aparente=round(ap, 3),
                      vacios_pct=round(float(np.mean(M["vacios_pct"])), 1),
                      seca_sobre_nominal=round(seca / nominal, 3), aparente_sobre_nominal=round(ap / nominal, 3),
                      seca_sobre_aparente=round(seca / ap, 3))
    return out


# ------------------------------------------------------------------ linac (NCRP 151)
TVL_PRI = {"6MV": (37, 33), "10MV": (41, 37), "15MV": (44, 41)}       # NCRP 151 B.2, hormigón 2.35
TVL_FUGA = {"6MV": (34, 29), "10MV": (35, 31), "15MV": (36, 33)}      # NCRP 151 B.7 (fuga)


def espesor(B, tv):
    n = -math.log10(B)
    return tv[0] + max(0.0, n - 1) * tv[1], n


def linac(bd, dens):
    W, P = 30 * 2 * 5 * 3.0, 0.02e-3                                   # Gy/sem; Sv/sem (público)
    D = bd["DWG_medido"]["linac"]
    geo = {"primario_lateral": dict(d=5.46, U=0.25, T=1.0, tipo="pri", dwg=D["primario_cm"]),
           "techo_sala_espera": dict(d=3.46, U=0.25, T=1.0, tipo="pri", dwg=D["losa_cm"]),
           "secundario_norte_fuga": dict(d=3.99, U=1.0, T=1.0, tipo="fuga", dwg=39)}
    rho = {"nominal_5.5": 5.5, "nominal_5.0": 5.0, "NIPOL_5_real": dens["tabique_NIPOL_5"]["seca"],
           "NIPOL_5.5_real_est": round(5.5 * dens["tabique_NIPOL_5"]["seca_sobre_aparente"], 2)}
    res = {}
    for k, g in geo.items():
        fila = {}
        for e in TVL_PRI:
            if g["tipo"] == "pri":
                t, n = espesor(P * g["d"] ** 2 / (W * g["U"] * g["T"]), TVL_PRI[e])
            else:
                t, n = espesor(P * g["d"] ** 2 / (1e-3 * W * g["T"]), TVL_FUGA[e])
            fila[e] = dict(n_TVL=round(n, 2), hormigon_cm=round(t, 1),
                           tabique_cm={r: round(t * 2.35 / v, 1) for r, v in rho.items()},
                           tabique_cm_credito10={r: round(0.9 * t * 2.35 / v, 1) for r, v in rho.items()})
        # lo dibujado (supuesto 5.5) construido con tabique "5" real: equivalente en hormigón
        eq = g["dwg"] * dens["tabique_NIPOL_5"]["seca"] / 2.35
        eq55 = g["dwg"] * 5.5 / 2.35
        res[k] = dict(geometria=g, requerido=fila, DWG_cm=g["dwg"], DWG_eq_hormigon_cm_si_NIPOL5=round(eq, 1),
                      DWG_eq_hormigon_cm_si_5_5=round(eq55, 1))
    # reescalado de los casos GAMMA a la densidad real del tabique 5
    c = bd["estimaciones_GAMMA"]["linac"]["casos"]; s = dens["tabique_NIPOL_5"]["seca"]
    esc = {"GAMMA_5.0_calc_x(5.0/real)": [round(v * 5.0 / s, 1) for v in c["2_5.0_calc_h3.5"]],
           "GAMMA_5.5_calc_x(5.5/real)": [round(v * 5.5 / s, 1) for v in c["3_5.5_calc_h3.5"]]}
    esc["modulos_13cm_desde_5.0"] = [modulo(v) for v in esc["GAMMA_5.0_calc_x(5.0/real)"]]
    esc["orden_caras"] = bd["estimaciones_GAMMA"]["linac"]["orden_caras"]
    alturas = {"h_int_3.30+losa": {k: round(3.30 + v / 100 + 0.10 + 1.00, 2) for k, v in
                                    zip(("losa_5.0x", "losa_5.5x"), (esc["GAMMA_5.0_calc_x(5.0/real)"][-1], esc["GAMMA_5.5_calc_x(5.5/real)"][-1]))},
               "entrepiso_m": 5.40}
    return dict(W_Gy_sem=W, P_Sv_sem=P, densidades=rho, barreras=res, GAMMA_reescalado=esc, alturas=alturas)


# ------------------------------------------------------------------ ciclotrón (Geant4 losa_tvl)
MATS = {"ORD_235": ("concreto ordinario 2.35", 2.35), "ORD_250": ("concreto ordinario 2.50", 2.50),
        "MAG_332": ("tabique 3.5 (3.32 real) hipótesis magnetita", 3.32), "BAR_332": ("tabique 3.5 (3.32 real) hipótesis barita", 3.32)}


def leer_losa(m):
    fs = sorted(glob.glob(str(LOSA / f"res_{m}_s*.txt")))
    if not fs:
        return None
    A = []; N = []
    for f in fs:
        hdr = open(f).readline().split(); N.append(float(hdr[hdr.index("N") + 1]))
        A.append(np.loadtxt(f))
    N = np.array(N); w = N / N.sum()
    z = A[0][:, 0]
    Hn = sum(wi * a[:, 1] for wi, a in zip(w, A)); Hg = sum(wi * a[:, 3] for wi, a in zip(w, A))
    sn = np.sqrt(sum((wi * a[:, 2]) ** 2 for wi, a in zip(w, A))); sg = np.sqrt(sum((wi * a[:, 4]) ** 2 for wi, a in zip(w, A)))
    th = sum(wi * a[:, 5] for wi, a in zip(w, A))
    return dict(z=z, Hn=Hn, Hg=Hg, sn=sn, sg=sg, H=Hn + Hg, sH=np.hypot(sn, sg), th=th, N=float(N.sum()), md5=[md5(f) for f in fs])


def ciclotron(bd):
    R = {}
    for m, (nombre, rho) in MATS.items():
        L = leer_losa(m)
        if L is None:
            R[m] = {"estado": "sin_corridas"}; continue
        z, H, sH = L["z"], L["H"], L["sH"]
        ok = (z >= 45) & (z <= 175) & (H > 0) & (sH < 0.5 * H)
        p = np.polyfit(z[ok], np.log10(H[ok]), 1, w=1 / np.maximum(sH[ok] / H[ok] / math.log(10), 1e-3))
        tvl = -1 / p[0]
        R[m] = dict(nombre=nombre, rho=rho, historias=L["N"], TVL_cm=round(tvl, 1), TVL_g_cm2=round(tvl * rho, 1),
                    frac_gamma_150cm=round(float(L["Hg"][z == 145][0] / L["H"][z == 145][0]), 3) if (z == 145).any() else None,
                    term_150cm=float(L["th"][z == 145][0]) if (z == 145).any() else None,
                    perfil=[dict(z=float(a), H=float(b), sH=float(c), Hn=float(d), Hg=float(e), phi_term=float(f))
                            for a, b, c, d, e, f in zip(z, H, sH, L["Hn"], L["Hg"], L["th"])],
                    md5=L["md5"], ajuste=dict(a=float(p[1]), b=float(p[0])))
    # espesor equivalente a los muros IBA/GAMMA y al requerido (TVL kiube): ref. hormigón 2.35 de F85
    ref = R.get("ORD_235", {})
    if "TVL_cm" in ref:
        def t_equiv(t_ref_cm, m):
            # mismo log10(H) que la referencia con espesor t_ref en ORD_235
            a0, b0 = ref["ajuste"]["a"], ref["ajuste"]["b"]; a1, b1 = R[m]["ajuste"]["a"], R[m]["ajuste"]["b"]
            return (a0 + b0 * t_ref_cm - a1) / b1
        G = bd["estimaciones_GAMMA"]["ciclotron"]
        req = {"muro_publico_T1_0.5uSv_h": 183, "muro_restriccion_0.3mSv": 196, "techo_azotea_T1_40_1mSv": 146,
               "techo_azotea_T1_40_0.3mSv": 160, "IBA_oeste": 240, "IBA_este": 220, "IBA_sur": 250, "IBA_techo": 230}
        R["equivalencias_cm"] = {k: {m: round(t_equiv(v, m), 0) for m in MATS if "ajuste" in R.get(m, {})} for k, v in req.items()}
        R["nota_equivalencias"] = ("espesor de cada material con la MISMA H*(10) transmitida que el hormigón 2.35 de referencia "
                                   "(requeridos de F85/zumaya escalados a 300 µA, 2000 h/año); fuera de 45–175 cm es extrapolación")
    return R


def ejecutar():
    OUT.mkdir(parents=True, exist_ok=True)
    bd = json.load(open(BD))
    dens = densidades(bd)
    out = {"fase": 86, "version": "3.12.0", "tipo": "simulacion_teorica", "pq": "no_declarada_nunca",
           "fecha": datetime.datetime.now().isoformat(timespec="seconds"), "bd": str(BD.relative_to(RAIZ)), "md5_bd": md5(BD),
           "densidades": dens, "linac": linac(bd, dens), "ciclotron": ciclotron(bd),
           "advertencias": [
               "Los informes IMCYC no contienen composición química ni TVL del proveedor: ambos quedan pendiente_fuente.",
               "Ensayo NMX-C-263 fuera del alcance de acreditación ema; muestreo no responsabilidad del IMCYC; mismo OT/IT para 3 clientes distintos (2022).",
               "Linac: equivalencia por espesor másico (conservadora para fotones de MV; el agregado de alto Z da a lo más ~10 % de crédito, mostrado aparte).",
               "Ciclotrón: haz delgado normal sobre losa semi-infinita (H*(10) en haz ancho por reciprocidad); composición del tabique 3.5 en dos hipótesis (magnetita/barita) hasta tener la ficha.",
               "Mampostería: juntas de mortero y 12–22 % de vacíos no se modelan (material homogéneo a la densidad volumétrica).",
           ]}
    json.dump(out, open(OUT / "blindaje_zumaya_f86.json", "w"), indent=1, ensure_ascii=False, default=float)
    with open(OUT / "registro_materiales.jsonl", "a") as f:
        for k, d in dens.items():
            f.write(json.dumps({"fecha": out["fecha"], "material": k, "supuesto_previo": f"densidad {d['nominal']} g/cm3 (nominal)",
                                "valor_medido_blindaje": d["seca"], "estado": "discrepancia_cuantificada",
                                "nota": "nominal = masa específica aparente; blindaje = volumétrica seca"}, ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":
    o = ejecutar()
    print(json.dumps(o["densidades"], indent=1))
    for k, v in o["linac"]["barreras"].items():
        print(k, "DWG", v["DWG_cm"], "eq_horm(NIPOL5)", v["DWG_eq_hormigon_cm_si_NIPOL5"], {e: (r["hormigon_cm"], r["tabique_cm"]["NIPOL_5_real"]) for e, r in v["requerido"].items()})
    print(o["linac"]["GAMMA_reescalado"]); print(o["linac"]["alturas"])
    for m, r in o["ciclotron"].items():
        if isinstance(r, dict) and "TVL_cm" in r:
            print(m, r["TVL_cm"], r["TVL_g_cm2"], r["frac_gamma_150cm"], r["term_150cm"], r["historias"])
    print(json.dumps(o["ciclotron"].get("equivalencias_cm"), indent=0))
