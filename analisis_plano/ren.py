import json,numpy as np,matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import sys
g=np.load('geom.npz');t=json.load(open('textos.json'));C=t['capas'];L=g['lays'];S=g['segs']
x0,x1,y0,y1=map(float,sys.argv[1:5]); out=sys.argv[5]; dpi=int(sys.argv[6]) if len(sys.argv)>6 else 200
col={'CONTRAVENTEOS':'red','PILAS':'magenta','TABIQUES BLINDADOS':'blue','BUNKER':'darkorange','CYCLOTRON':'green','LOSA BLINDADA':'cyan','COLUMNAS':'black','MUROS':'k','Wall concrete':'brown','EJES':'0.6'}
fig,ax=plt.subplots(figsize=(16,16*(y1-y0)/(x1-x0)))
m=(np.maximum(S[:,0],S[:,2])>x0)&(np.minimum(S[:,0],S[:,2])<x1)&(np.maximum(S[:,1],S[:,3])>y0)&(np.minimum(S[:,1],S[:,3])<y1)
for i,n in enumerate(C):
  k=m&(L==i)
  if not k.any(): continue
  c='0.75';lw=0.3
  for key,v in col.items():
    if n.endswith('$'+key) or n==key: c=v;lw=1.2
  ax.add_collection(LineCollection(S[k].reshape(-1,2,2),colors=c,linewidths=lw))
for x,y,h,r,l,s,top in t['textos']:
  if x0<x<x1 and y0<y<y1 and s.strip(): ax.text(x,y,s[:40],fontsize=5,rotation=r)
ax.set_xlim(x0,x1);ax.set_ylim(y0,y1);ax.set_aspect('equal');plt.savefig(out,dpi=dpi,bbox_inches='tight')
