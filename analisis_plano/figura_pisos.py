"""Planta por nivel (PB, N1, N2, N3) en coordenadas de PB (ejes alineados por columnas), muros/blindajes/columnas/
contraventeos del DWG BIND 28-10-26 y huella de los recintos blindados de PB superpuesta en los niveles superiores."""
import json, re, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle

D = "/home/claude/plano/v13/"
Z = np.load(D + "geom.npz"); S = Z["segs"]; Ly = Z["lays"]; T = json.load(open(D + "textos.json")); C = T["capas"]
OFF = {"PB": 0.0, "N1": 98.94, "N2": 201.56, "N3": 290.57}
XREF = {"PB": ("XREF PB NEURO-ONCOLOGIA", "XREF RADIOFARMACIA"), "N1": ("XREF 1N NEURO-ONCOLOGIA",),
        "N2": ("XREF 2N NEURO-ONCOLOGIA",), "N3": ("XREF 3N NEURO-ONCOLOGIA",)}
NPT = {"PB": "+10.35", "N1": "+15.75", "N2": "+21.15", "N3": "+26.55 (est.)"}


def estilo(c):
    u = c.upper()
    if "COLUMNA" in u or "CG-M-WALL" in u: return ("#555", 0.6)
    if "CONTRAVENT" in u: return ("#e08a00", 0.9)
    if "TABIQUES BLIND" in u or "PLOMO" in u or "BUNKER" in u: return ("#1f4fd1", 1.6)
    if "LOSA BLIND" in u: return ("#b0219e", 1.0)
    if re.search(r"\$MUROS$|\$MUROS DE TABLAROCA$|MUROS BAJOS", u): return ("#222", 0.5)
    if "PUERTA" in u: return ("#aaa", 0.3)
    return None


EST = [estilo(c) for c in C]
ROT = {"PB": [("CICLOTRÓN", -11.5, 41.5), ("RADIOFARMACIA", 6, 43), ("GAMMA KNIFE", 25.3, 37.2), ("LINAC", 41, 49.1),
              ("control", 31, 36.5), ("jardín", 23.5, 32.3)],
       "N1": [("AZOTEA", -11.5, 41.5), ("PET/CT", 2.6, 37.5), ("inyección", -1.5, 44.5), ("simulador CT", 2, 45),
              ("cuarto caliente", 16.5, 35.3), ("BRAQUITERAPIA", 25.3, 37.2), ("sala de espera", 33.5, 47.6),
              ("IDF / tab. eléct.", 38.6, 46.5), ("C.A.A.", 42, 50.5), ("enfermeras", 42, 41.3)],
       "N2": [("gammacámara", -0.5, 43), ("inyecciones", -3.5, 36), ("cuarto caliente", 2.8, 47.3), ("YODO", 8.6, 37.6),
              ("sanit. públicos", 26.4, 37.3), ("consultorios", 9.3, 46.6), ("sala de espera", 38, 41.5)],
       "N3": [("biología molecular", 13.4, 36.4), ("PCR", 9.5, 35.3), ("enfermería", -0.9, 43.5),
              ("patología", 33, 42.5), ("sanitarios", 24, 36.9)]}
HUELLAS = {"linac": [(36.89, 42.36, 45.19 - 36.89, 52.82 - 42.36)], "GK": [(21.89, 34.20, 28.87 - 21.89, 40.58 - 34.20)],
           "ciclotrón (zona, muros no dibujados)": [(-17.0, 33.1, 11.7, 16.0)]}

fig, axs = plt.subplots(4, 1, figsize=(15, 23))
for ax, (niv, off) in zip(axs, OFF.items()):
    x0, x1, y0, y1 = -19 + off, 50 + off, 31.5 + 0, 56.5
    m = ((np.minimum(S[:, 0], S[:, 2]) < x1) & (np.maximum(S[:, 0], S[:, 2]) > x0) &
         (np.minimum(S[:, 1], S[:, 3]) < y1) & (np.maximum(S[:, 1], S[:, 3]) > y0))
    keep = np.array([EST[l] is not None and any(C[l].replace("HATCH:", "").startswith(x) for x in XREF[niv]) for l in Ly]) & m
    idx = np.where(keep)[0]
    seg = S[idx].reshape(-1, 2, 2).copy(); seg[:, :, 0] -= off
    ax.add_collection(LineCollection(seg, colors=[EST[Ly[i]][0] for i in idx], linewidths=[EST[Ly[i]][1] for i in idx]))
    for name, rs in HUELLAS.items():
        for (x, y, w, h) in rs:
            ax.add_patch(Rectangle((x, y), w, h, fill=niv == "PB" and False, ec="#d0182a", lw=1.4 if niv != "PB" else 0.8,
                                   ls="--", alpha=0.9))
    for t, x, y in ROT[niv]:
        ax.text(x, y, t, ha="center", va="center", fontsize=8.5, color="#111",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))
    # anotaciones de blindaje del DWG (texto h=… y BARRERA…)
    for x, y, h, r, l, s, top in T["textos"]:
        if x0 < x < x1 and y0 < y < y1 and (("g/cm3" in s) or ("BARRERA" in s) or ("plomo" in s)) and top is None or (
                x0 < x < x1 and y0 < y < y1 and isinstance(top, str) and top.startswith(XREF[niv][0]) and (("g/cm3" in s) or "BARRERA" in s or "plomo" in s)):
            ax.text(x - off, y, s.replace("\n", " ").replace("(BARRERA DE ", "(").replace(" = ", " "), fontsize=5.2, color="#1f4fd1")
    ax.set_xlim(-19, 50); ax.set_ylim(y0, y1); ax.set_aspect("equal")
    ax.set_title(f"{niv}  —  N.P.T. {NPT[niv]} m   (rojo discontinuo: huella de linac, Gamma Knife y zona del ciclotrón de PB)", fontsize=10, loc="left")
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values(): sp.set_visible(False)
axs[-1].plot([], [], color="#1f4fd1", lw=1.6, label="tabiques blindados / plomo / búnker")
axs[-1].plot([], [], color="#b0219e", lw=1, label="losa blindada")
axs[-1].plot([], [], color="#e08a00", lw=1, label="contraventeos")
axs[-1].plot([], [], color="#555", lw=0.6, label="columnas 1,0×1,0 m")
axs[-1].plot([], [], color="#222", lw=0.5, label="muros / tablaroca")
axs[-1].legend(loc="lower right", fontsize=8, ncol=5, frameon=False, bbox_to_anchor=(1, -0.12))
fig.tight_layout(); fig.savefig("/home/claude/plano/pisos_blindajes.png", dpi=110, facecolor="w")
print("ok")
