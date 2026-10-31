import json, numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
o=json.load(open('/tmp/claude-0/-home-claude/048fd5ce-4ee1-53cc-84c5-12e7883f45b1/scratchpad/evidencia_v072/fase86/blindaje_zumaya_f86.json'))['ciclotron']
lab={'ORD_235':('Concreto ordinario 2,35','#2a6fdb'),'ORD_250':('Concreto ordinario 2,50','#16a085'),'MAG_332':('Tabique «3,5» (3,32 real), hip. magnetita','#d35400'),'BAR_332':('Tabique «3,5» (3,32 real), hip. barita','#8e44ad')}
fig,ax=plt.subplots(1,2,figsize=(12,4.8))
for m,(n,c) in lab.items():
    r=o[m]; z=np.array([p['z'] for p in r['perfil']]); H=np.array([p['H'] for p in r['perfil']]); s=np.array([p['sH'] for p in r['perfil']])
    ok=(H>0)&(s<0.6*H)&(z<=185)
    ax[0].errorbar(z[ok],H[ok],s[ok],fmt='o-',ms=3,lw=1.2,capsize=2,color=c,label=f"{n}: TVL {r['TVL_cm']:.1f} cm")
    ax[1].plot(z[ok]*r['rho'],H[ok],'o-',ms=3,lw=1.2,color=c,label=f"{r['TVL_g_cm2']:.0f} g/cm² por TVL")
ax[0].set_yscale('log'); ax[1].set_yscale('log')
ax[0].set_xlabel('espesor [cm]'); ax[1].set_xlabel('espesor másico [g/cm²]')
ax[0].set_ylabel('H*(10) n+γ por neutrón incidente [pSv·cm²]')
ax[0].set_title('Por centímetro: los cuatro materiales casi coinciden',fontsize=10,loc='left')
ax[1].set_title('Por masa: el tabique pesado rinde peor (poco hidrógeno)',fontsize=10,loc='left')
for a in ax: a.grid(alpha=.3,which='both'); a.legend(fontsize=8,frameon=False)
fig.suptitle('Transmisión del espectro 18O(p,n) BON21 (ciclotrón 18 MeV) — Geant4 QGSP_BIC_HP, haz ancho normal',fontsize=10)
fig.tight_layout(); fig.savefig('losas_ciclotron.png',dpi=120,facecolor='w'); print('ok')
