import json,numpy as np,matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
g=np.load('geom.npz');t=json.load(open('textos.json'));C=t['capas'];L=g['lays'];S=g['segs']
x0,x1,y0,y1=-16,49,30.8,56
fig,ax=plt.subplots(figsize=(17,7))
m=(np.maximum(S[:,0],S[:,2])>x0)&(np.minimum(S[:,0],S[:,2])<x1)&(np.maximum(S[:,1],S[:,3])>y0)&(np.minimum(S[:,1],S[:,3])<y1)
sty={'CONTRAVENTEOS':('#d62728',1.6),'PILAS':('#9467bd',1.6),'TABIQUES BLINDADOS':('#1f4fd6',1.4),'CYCLOTRON':('#2ca02c',1.4),'COLUMNAS':('#222',0.9),'ZANJA':('#ff7f0e',1.2)}
skip=['Gamma_Knife','EQUIPO','Mobiliario','MOBILIARIO','G-IMPT','LAMPARAS','PLAFONES','Linac_Equipment','PR-FURN','HATCH']
for i,n in enumerate(C):
  k=m&(L==i)
  if not k.any(): continue
  c,lw='#c8c8c8',0.25
  for key,v in sty.items():
    if n.endswith('$'+key): c,lw=v
  if c=='#c8c8c8' and any(s in n for s in skip): continue
  ax.add_collection(LineCollection(S[k].reshape(-1,2,2),colors=c,linewidths=lw))
A=dict(fontsize=8.5,ha='center')
ax.text(-10.3,31.9,'CICLOTRÓN: bóveda 4.00×4.00\nO 2.40 · E 2.20 · S 2.50 (tapón) · laberinto N 7.23',**A,color='#2ca02c')
ax.annotate('pila Ø1.00\n(bajo el ciclotrón)',(-10.3,38.1),(-15.5,52.5),fontsize=8,color='#9467bd',arrowprops=dict(arrowstyle='->',color='#9467bd'))
ax.annotate('junta constructiva +\ncontraventeo NA (N1–N3):\ncruce de la zanja de\nlíneas de transferencia',(-5.8,38),(-2.5,51.5),fontsize=8,color='#d62728',arrowprops=dict(arrowstyle='->',color='#d62728'))
ax.text(7,42,'RADIOFARMACIA\n(sin distribución en este plano)',**A,color='#777')
ax.text(40.8,48.6,'LINAC\nmuros 0.65 / 0.39 m\n(req. TD-550 real: 1.04–1.17)',**A,color='#1f4fd6')
ax.text(25.2,37.3,'GAMMA KNIFE\n0.26 / 0.13 m\ncontraventeos N, E, S',**A,color='#1f4fd6')
ax.legend(handles=[Line2D([],[],color=v[0],lw=2,label=k.title()) for k,v in sty.items()],loc='lower right',fontsize=8,ncol=6,frameon=False,bbox_to_anchor=(1,-0.16))
ax.set_xlim(x0,x1);ax.set_ylim(y0,y1);ax.set_aspect('equal');ax.set_xlabel('x [m]');ax.set_ylabel('y [m]')
ax.set_title('Planta baja AR-IN-PB-1-01 (31/10/2026): contraventeos, pilas y blindajes',fontsize=11,loc='left')
plt.savefig('pb_contraventeos.png',dpi=170,bbox_inches='tight')
