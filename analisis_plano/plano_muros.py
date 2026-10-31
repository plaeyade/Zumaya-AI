import sys, json, re, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
Z=np.load("geom.npz"); S=Z["segs"]; Ly=Z["lays"]; T=json.load(open("textos.json")); C=T["capas"]
x0,x1,y0,y1=map(float,sys.argv[1:5]); out=sys.argv[5]; dpi=int(sys.argv[6])
pat0=re.compile(r"MURO|BUNKER|TABIQUE|COLUMNA|CONTRAVENT|WALL|PLOMO|Bunker|CANCEL|PUERTA|HATCH", re.I)
estilo=[]
for c in C:
    u=c.upper()
    if "COLUMNA" in u: estilo.append(("#d00",1.2))
    elif "CONTRAVENT" in u: estilo.append(("#f80",1.2))
    elif "LOSA BLIND" in u: estilo.append(("#c0c",1.0))
    elif "BUNKER" in u or "TABIQUES BLIND" in u or "PLOMO" in u: estilo.append(("#00c",1.4))
    elif "MURO" in u or "WALL" in u: estilo.append(("#000",1.0))
    elif "PUERTA" in u or "CANCEL" in u: estilo.append(("#999",0.5))
    elif c.startswith("DIM:"): estilo.append(("#0a0",0.4))
    elif "EJES" in u: estilo.append(("#fbb",0.3))
    else: estilo.append(None)
m=((np.minimum(S[:,0],S[:,2])<x1)&(np.maximum(S[:,0],S[:,2])>x0)&(np.minimum(S[:,1],S[:,3])<y1)&(np.maximum(S[:,1],S[:,3])>y0))
keep=np.array([estilo[l] is not None for l in Ly]) & m
w,h=x1-x0,y1-y0; sc=min(2.0, 60/max(w,h))
fig=plt.figure(figsize=(w*sc,h*sc)); ax=fig.add_axes([0,0,1,1])
idx=np.where(keep)[0]
ax.add_collection(LineCollection(S[idx].reshape(-1,2,2),colors=[estilo[Ly[i]][0] for i in idx],linewidths=[estilo[Ly[i]][1] for i in idx]))
for x,y,hh,r,lay,s,top in T["textos"]:
    if x0<x<x1 and y0<y<y1 and s.strip() and (top is None or "HZ" not in top):
        ax.text(x,y,s.replace("\n"," ")[:45],fontsize=7 if not lay.startswith("DIM") else 6,color="k" if not lay.startswith("DIM") else "g")
ax.set_xlim(x0,x1); ax.set_ylim(y0,y1); ax.set_aspect("equal"); ax.axis("off")
fig.savefig(out,dpi=dpi,facecolor="w"); print(len(idx))
