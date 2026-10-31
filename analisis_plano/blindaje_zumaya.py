"""Re-cálculo independiente (orden de magnitud, supuestos declarados) de las barreras de GAMMA (Zumaya 28-10-26)
con la geometría extraída del DWG BIND 28-10-26. Salida: blindaje_zumaya.json
- Linac: NCRP 151 (barrera primaria de techo) en función de energía y factor de ocupación T.
- HDR (Ir-192): SRS-47 / NCRP 151, W = RAKR·A·t·n, por muro, con P público 0,02 y controlado 0,1 mSv/sem.
- Ciclotrón: escalado del MC kiube v0.35 (F85, Geant4, hormigón 2,35) a 300 µA y 8 h/día.
"""
import json, math

out = {}
# ---------------- LINAC (Elekta según bloques del DWG; energía no declarada por GAMMA) -----------------
W = 30 * 2 * 5 * 3.0          # Gy/sem en isocentro: 30 pac/jornada × 2 turnos × 5 d × 3 Gy
U = 0.25
iso_h = 1.24                  # m sobre piso (Elekta)
h_int = 3.30                  # DWG, CORTE GENERAL 03
d_roof = (h_int - iso_h - 1.0) + 1.00 + 0.10 + 1.00 + 0.30   # blanco→0,3 m sobre piso N1 (losa búnker 1,00 + holgura + entrepiso 1,00)
TVL = {"6MV": (37, 33), "10MV": (41, 37), "15MV": (44, 41), "18MV": (45, 43)}   # NCRP 151 Tabla B.2, hormigón 2,35, primario
lin = {"W_Gy_sem": W, "U": U, "d_techo_m": round(d_roof, 2), "P_mSv_sem": 0.02, "casos": {}}
for T_name, T in (("sala_de_espera_T1", 1.0), ("area_verde_con_bancas_T1_20", 1 / 20), ("area_verde_transito_T1_40", 1 / 40)):
    for e, (t1, te) in TVL.items():
        B = 0.02e-3 * d_roof ** 2 / (W * U * T)        # Gy: P en Sv≈Gy
        n = -math.log10(B)
        t235 = t1 + (n - 1) * te
        lin["casos"][f"{T_name}|{e}"] = dict(B=B, n_TVL=round(n, 2), hormigon_235_cm=round(t235, 1),
                                             escalado_masa_55_cm=round(t235 * 2.35 / 5.5, 1),
                                             cabe_con_h_int_3_30_en_5_40=bool(h_int + t235 / 100 <= 5.40 - 0.10))
lin["DWG"] = {"h_int_m": 3.30, "losa_m": 1.00, "losa_eq_235_cm_si_5_5": round(100 * 5.5 / 2.35, 1),
              "muro_primario_cm": 65, "franja_primaria_m": 4.10, "secundarios_cm": 39, "laberinto_cm": [30, 26]}
# ancho de franja primaria (NCRP 151): w = 0,566·d + 0,6 (campo 40×40 girado 45°)
iso = (41.025, 49.125); cara_ext_E = 45.19
d_w = cara_ext_E - (iso[0] - 1.0)
lin["franja_primaria_requerida_m"] = round(0.566 * d_w + 0.6, 2)
lin["franja_primaria_centro_vs_iso_m"] = round((47.08 + 51.18) / 2 - iso[1], 3)
out["linac"] = lin

# ---------------- HDR Ir-192 (N1, encima del Gamma Knife) -----------------
A_GBq = 370.0                     # 10 Ci (no declarado por GAMMA; valor típico de carga máxima)
RAKR = 0.111                      # mGy·m²/(GBq·h)
t_h = 50 * 25 / 60                # 50 pac/sem × 25 min
Wb = RAKR * A_GBq * t_h           # mGy/sem a 1 m
TVL_ir = 15.0                     # cm hormigón 2,35 (Ir-192, haz ancho); 3,5 g/cm³ escala por densidad
src = (24.2, 37.4)                # zona de tratamiento al oeste del tabique interior (x 26,09–26,35), centro en y
caras = {  # nombre: (distancia fuente→0,3 m tras la cara exterior, espesor DWG cm a 3,5, colindancia, T, controlada)
    "oeste_cuarto_caliente": (src[0] - 21.89 + 0.3, 39, "cuarto caliente", 1.0, True),
    "norte_pasillo_vestibulo": (40.71 - src[1] + 0.3, 52, "pasillo/vestíbulo", 1.0, False),
    "sur_fachada": (src[1] - 34.20 + 0.3, 39, "fachada exterior N1", 1 / 40, False),
    "este_control_via_tabique": (28.87 - src[0] + 0.3, 13 + 26, "sala de control (tras tabique interior 26 + muro 13)", 1.0, True),
    "techo_sanitarios_publicos_N2": (5.40 - 1.0 + 0.3, 39, "sanitarios públicos N2", 1 / 20, False),
    "piso_gamma_knife_PB": (1.0 + 3.70, 70 * 2.35 / 3.5, "sala Gamma Knife (controlada)", 1.0, True),
}
hdr = {"W_mGy_sem_1m": round(Wb, 1), "fuente": src, "TVL_235_cm": TVL_ir, "caras": {}}
for k, (d, prov35, col, T, ctrl) in caras.items():
    res = {}
    for nP, P in (("publico_0.02", 0.02), ("controlado_0.1", 0.1)):
        for nT, TT in (("T1", 1.0), ("T_real", T)):
            B = P * d * d / (Wb * TT)
            n = max(0.0, -math.log10(B))
            res[f"{nP}|{nT}"] = dict(n=round(n, 2), cm_235=round(n * TVL_ir, 1), cm_35=round(n * TVL_ir * 2.35 / 3.5, 1))
    hdr["caras"][k] = dict(d_m=round(d, 2), colindancia=col, T=T, controlada=ctrl, DWG_cm_35=round(prov35, 1), req=res)
out["hdr"] = hdr

# ---------------- CICLOTRÓN (escalado del MC kiube v0.35 F85) -----------------
I_ref, I = 180.0, 300.0
ext_211 = {"oeste": 0.00518, "este": 0.0120, "sur": 0.00597, "norte": 0.00509, "norte_parche": 0.0242}  # µSv/h a 180 µA, 2,11 m
TVLc = 26.0
horas = 8 * 250
ciclo = {"horas_haz_ano": horas, "uAh_ano": I * horas, "TVL_cm_235": TVLc, "muros": {}, "techo": {}}
for k, v in ext_211.items():
    h300 = v * I / I_ref
    ciclo["muros"][k] = dict(ext_2_11m_300uA_uSv_h=round(h300, 4), anual_mSv=round(h300 * horas / 1000, 4))
for tgt_name, tgt in (("0.5_uSv_h_publico_T1", 0.5), ("0.15_uSv_h_restriccion_0.3mSv", 0.15)):
    h = max(ext_211.values()) * I / I_ref
    ciclo["muros"][f"espesor_235_para_{tgt_name}_cm"] = round(211 - TVLc * math.log10(tgt / h), 0)
# techo: no hay cuentas directas en el MC (techo sin sesgo) → calibración con muros: H_ext = C·H_int·10^(-t/TVL)
C = max(0.0120 / (3.375e6 * 10 ** (-211 / TVLc)), 0.0242 / (6.415e6 * 10 ** (-211 / TVLc)))
H_int_techo = 1.0e7 * I / I_ref    # µSv/h bajo el techo (conservador: > máximo en caras de muros 6,4e6 a 180 µA)
for nm, tgt in (("azotea_T1_40_1mSv", 1.0e3 / (horas / 40)), ("azotea_T1_40_0.3mSv", 0.3e3 / (horas / 40)),
                ("ocupable_T1_0.5uSv_h", 0.5)):
    ciclo["techo"][nm] = dict(H_obj_uSv_h=round(tgt, 2), espesor_235_cm=round(TVLc * math.log10(C * H_int_techo / tgt), 0))
ciclo["techo"]["C_calibracion"] = round(C, 3)
ciclo["techo"]["IBA_GAMMA_cm"] = 230
ciclo["muros"]["IBA_GAMMA_cm"] = {"oeste": 240, "este": 220, "sur_tapon": 250}
out["ciclotron"] = ciclo
json.dump(out, open("/home/claude/plano/blindaje_zumaya.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(out, indent=1, ensure_ascii=False))
