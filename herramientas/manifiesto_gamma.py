"""Genera gamma-ingesta.json (contrato gamma/ingesta@1, ADR-0034 de GAMMA-AI) para fuentes/.

Uso: python herramientas/manifiesto_gamma.py   (desde la raíz del repo)
Verificar con GAMMA:  gamma ecosistema validar gamma-ingesta.json --raiz-productor .
Sólo stdlib. Los metadatos por carpeta están en CATALOGO; un archivo sin entrada falla.
"""
import datetime
import hashlib
import json
import mimetypes
import pathlib
import subprocess

RAIZ = pathlib.Path(__file__).resolve().parents[1]
FUENTES = RAIZ / "fuentes"
mimetypes.add_type("image/vnd.dwg", ".dwg")

# carpeta → (dominio, gobernanza, emisor, licencia)
CATALOGO = {
    "ciclotron_IBA": ("radioproteccion/ciclotron", "restricted", "IBA", "documentacion de fabricante; uso interno"),
    "blindaje_GAMMA": ("radioproteccion/blindajes", "governed", "GAMMA (proyectista)", "propietario; uso interno"),
    "tabiques": ("materiales/blindaje", "governed", "fabricante de tabiques", "ficha tecnica comercial"),
    "geotecnia": ("estructura/geotecnia", "governed", "laboratorio de mecanica de suelos", "propietario; uso interno"),
    "planos": ("arquitectura/planos", "restricted", "proyecto arquitectonico Zumaya", "propietario; uso interno"),
}


def main():
    docs = []
    for p in sorted(FUENTES.rglob("*")):
        if not p.is_file():
            continue
        carpeta = p.relative_to(FUENTES).parts[0]
        if carpeta not in CATALOGO:
            raise SystemExit(f"sin catálogo para {p.relative_to(RAIZ)}")
        dominio, gob, emisor, licencia = CATALOGO[carpeta]
        data = p.read_bytes()
        rel = p.relative_to(RAIZ).as_posix()
        docs.append({
            "id_local": rel.rsplit(".", 1)[0],
            "ruta": rel,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "mime": mimetypes.guess_type(p.name)[0] or "application/octet-stream",
            "titulo": p.stem.replace("_", " "),
            "dominio": dominio,
            "gobernanza": gob,
            "tipo": "document",
            "emisor": emisor,
            "licencia": licencia,
            "jurisdiccion": "MX",
            "idioma": "en" if carpeta == "ciclotron_IBA" else "es",
        })
    try:
        commit = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=RAIZ,
                                capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        commit = None
    man = {"contrato": "gamma/ingesta@1",
           "productor": {"repo": "zumaya-ai", **({"commit": commit} if commit else {})},
           "generado_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "documentos": docs}
    (RAIZ / "gamma-ingesta.json").write_text(json.dumps(man, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"gamma-ingesta.json: {len(docs)} documentos")


if __name__ == "__main__":
    main()
