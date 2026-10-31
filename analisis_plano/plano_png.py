import sys, json, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
Z=np.load("geom.npz"); S=Z["segs"]; Ly=Z["lays"]; T=json.load(open("textos.json"))
caps=T["capas"]
x0,x1,y0,y1=map(float,sys.argv[1:5]); out=sys.argv[5]; dpi=int(sys.argv[6]) if len(sys.argv)>6 else 40
txt = len(sys.argv)>7
m=((np.minimum(S[:,0],S[:,2])<x1)&(np.maximum(S[:,0],S[:,2])>x0)&(np.minimum(S[:,1],S[:,3])<y1)&(np.maximum(S[:,1],S[:,3])>y0))
w,h=x1-x0,y1-y0; sc=min(1.0, 80/max(w,h))
fig=plt.figure(figsize=(w*sc,h*sc)); ax=fig.add_axes([0,0,1,1])
cm=plt.get_cmap("Dark2")
col=[cm(l%8) for l in Ly[m]]
ax.add_collection(LineCollection(S[m].reshape(-1,2,2),colors=col,linewidths=float(__import__("os").environ.get("LW","0.8"))))
if txt:
  for x,y,hh,r,lay,s,top in T["textos"]:
    if x0<x<x1 and y0<y<y1 and s.strip():
        ax.text(x,y,s.replace("\n"," ")[:40],fontsize=max(3,min(9,hh*30*sc)),color="k" if not lay.startswith("DIM") else "r")
ax.set_xlim(x0,x1); ax.set_ylim(y0,y1); ax.set_aspect("equal"); ax.axis("off")
fig.savefig(out,dpi=dpi,facecolor="w"); print(m.sum())
