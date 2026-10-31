"""Explota recursivamente el DXF: segmentos (x1,y1,x2,y2,capa) y textos (x,y,h,rot,capa,texto) en coordenadas de modelo."""
import sys, json, math, numpy as np
from ezdxf import recover
from ezdxf.math import Matrix44
doc, aud = recover.readfile(sys.argv[1])
msp = doc.modelspace()
segs, lays, texts = [], [], []
layidx = {}
def L(n):
    if n not in layidx: layidx[n] = len(layidx)
    return layidx[n]
def walk(entities, top, depth=0, lay0=None):
    for e in entities:
        t = e.dxftype()
        if lay0 and e.dxf.layer == '0': e.dxf.layer = lay0
        try:
            if t == "INSERT":
                if depth > 8: continue
                walk(e.virtual_entities(), top or e.dxf.name, depth + 1, e.dxf.layer)
                for a in e.attribs:
                    texts.append((a.dxf.insert.x, a.dxf.insert.y, a.dxf.height, 0, a.dxf.layer, a.dxf.text, top or e.dxf.name))
            elif t == "LINE":
                s, f = e.dxf.start, e.dxf.end; segs.append((s.x, s.y, f.x, f.y)); lays.append(L(e.dxf.layer))
            elif t in ("LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"):
                pts = None
                if t == "LWPOLYLINE" and not any(b for *_, b in e.get_points("xyseb")):
                    pts = [(p.x, p.y) for p in e.vertices_in_wcs()]
                    if e.closed: pts.append(pts[0])
                else:
                    import ezdxf.path as P
                    pts = [(v.x, v.y) for v in P.make_path(e).flattening(0.02)]
                for a, b in zip(pts[:-1], pts[1:]):
                    segs.append((a[0], a[1], b[0], b[1])); lays.append(L(e.dxf.layer))
            elif t == "HATCH":
                import ezdxf.path as P
                for pa in P.from_hatch(e):
                    pts=[(v.x,v.y) for v in pa.flattening(0.02)]
                    for a, b in zip(pts[:-1], pts[1:]):
                        segs.append((a[0], a[1], b[0], b[1])); lays.append(L("HATCH:"+e.dxf.layer))
            elif t in ("TEXT", "MTEXT"):
                s = e.plain_text() if t == "MTEXT" else e.dxf.text
                h = e.dxf.char_height if t == "MTEXT" else e.dxf.height
                texts.append((e.dxf.insert.x, e.dxf.insert.y, h, e.dxf.get("rotation", 0), e.dxf.layer, s, top))
            elif t == "DIMENSION":
                for v in e.virtual_entities():
                    if v.dxftype() in ("TEXT", "MTEXT"):
                        s = v.plain_text() if v.dxftype() == "MTEXT" else v.dxf.text
                        texts.append((v.dxf.insert.x, v.dxf.insert.y, 0.1, 0, "DIM:" + e.dxf.layer, s, top))
                    elif v.dxftype() == "LINE":
                        s, f = v.dxf.start, v.dxf.end; segs.append((s.x, s.y, f.x, f.y)); lays.append(L("DIM:" + e.dxf.layer))
        except Exception as ex:
            pass
walk(msp, None)
np.savez_compressed("geom.npz", segs=np.array(segs, float), lays=np.array(lays, int))
json.dump({"capas": list(layidx), "textos": texts}, open("textos.json", "w"), ensure_ascii=False)
print(len(segs), len(texts), len(layidx))
