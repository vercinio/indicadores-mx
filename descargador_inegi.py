"""Descargador de datos del INEGI (API de Indicadores).

Sirve para descubrir qué clave le corresponde a cada indicador y revisar
sus datos en Excel antes de usarlos en la página.

Comandos:
  python descargador_inegi.py catalogo
      Baja el catálogo completo de indicadores (BIE y BISE) a descargas/catalogo_*.csv
  python descargador_inegi.py buscar "precios al consumidor"
      Busca palabras en el catálogo ya descargado (sin acentos ni mayúsculas)
  python descargador_inegi.py serie 628229 [BIE|BISE] [AREA]
      Baja la serie histórica de una clave a descargas/serie_*.csv

El token se toma de la variable INEGI_TOKEN o se pide por teclado (no se muestra
ni se guarda). Los archivos .csv se abren directo en Excel; si tienes openpyxl
instalado (pip install openpyxl) también se crea un .xlsx.
"""
import csv
import getpass
import json
import os
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

CARPETA = Path(__file__).parent / "descargas"
BASE = "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/"
FUENTES = ("BIE-BISE", "BIE", "BISE")   # BIE-BISE: catálogo unificado desde el 1-dic-2025 (probar primero)
AREAS = ("00", "0700")


def obtener_token():
    return os.environ.get("INEGI_TOKEN") or getpass.getpass("Token del INEGI: ").strip()


def consultar(ruta, tok):
    """Pide una ruta de la API y devuelve el JSON (o None si falla)."""
    url = f"{BASE}{ruta}/{tok}?type=json"
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return json.loads(r.read().decode("utf-8-sig"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace").replace(tok, "***")[:200]
        print(f"   error {e.code}: {cuerpo}")
    except Exception as e:
        print(f"   no se pudo conectar: {type(e).__name__}")
    return None


def filas_de_catalogo(datos):
    """Busca dentro de la respuesta la primera lista de diccionarios (las filas)."""
    def buscar(x):
        if isinstance(x, list) and x and all(isinstance(i, dict) for i in x):
            return x
        if isinstance(x, dict):
            for v in x.values():
                r = buscar(v)
                if r:
                    return r
        return None
    return buscar(datos) or []


def _celda(v):
    return v if isinstance(v, (str, int, float)) or v is None else json.dumps(v, ensure_ascii=False)


def guardar(nombre, filas):
    CARPETA.mkdir(exist_ok=True)
    campos = []
    for f in filas:
        for k in f:
            if k not in campos:
                campos.append(k)
    ruta = CARPETA / f"{nombre}.csv"
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:   # utf-8-sig: Excel respeta los acentos
        w = csv.writer(fh)
        w.writerow(campos)
        for f in filas:
            w.writerow([_celda(f.get(c)) for c in campos])
    print(f"   guardado: {ruta} ({len(filas)} filas)")
    try:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(campos)
        for f in filas:
            ws.append([_celda(f.get(c)) for c in campos])
        wb.save(CARPETA / f"{nombre}.xlsx")
        print(f"   guardado: {CARPETA / (nombre + '.xlsx')}")
    except ImportError:
        pass


def cmd_catalogo():
    tok = obtener_token()
    for fuente in FUENTES:
        print(f"- Catálogo de indicadores {fuente} (puede tardar un poco)...")
        datos = consultar(f"CL_INDICATOR/null/es/{fuente}/2.0", tok)
        filas = filas_de_catalogo(datos)
        if not filas:
            print("   No pude leer filas. Respuesta recibida (primeros 400 caracteres):")
            print("  ", json.dumps(datos, ensure_ascii=False)[:400])
            continue
        print("   Ejemplo de filas:", filas[:2])
        guardar(f"catalogo_{fuente}", filas)


def _norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def cmd_buscar(palabras):
    archivos = sorted(CARPETA.glob("catalogo_*.csv"))
    if not archivos:
        sys.exit("Primero descarga el catálogo:  python descargador_inegi.py catalogo")
    claves = [_norm(p) for p in palabras.split()]
    total = 0
    for ar in archivos:
        with open(ar, encoding="utf-8-sig", newline="") as fh:
            for fila in csv.DictReader(fh):
                valores = [str(v or "") for v in fila.values()]
                if all(k in _norm(" ".join(valores)) for k in claves):
                    total += 1
                    if total <= 40:
                        print(ar.stem.replace("catalogo_", ""), "|", " | ".join(valores))
    extra = " (se muestran 40; afina la búsqueda)" if total > 40 else ""
    print(f"\n{total} coincidencias{extra}")


def cmd_serie(clave, fuentes, areas):
    tok = obtener_token()
    for fuente in fuentes:
        nombre = consultar(f"CL_INDICATOR/{clave}/es/{fuente}/2.0", tok)
        info = filas_de_catalogo(nombre) if nombre else []
        for area in areas:
            print(f"- Probando {fuente}, área {area}...")
            datos = consultar(f"INDICATOR/{clave}/es/{area}/false/{fuente}/2.0", tok)
            series = datos.get("Series") if isinstance(datos, dict) else None
            if not series:
                continue
            print(f"   ¡Funcionó! Nombre según el catálogo: {info[0] if info else '(no disponible)'}")
            filas = []
            for s in series:
                for o in s.get("OBSERVATIONS", []):
                    fila = {"INDICADOR": s.get("INDICADOR"), **o}
                    try:
                        fila["OBS_VALUE"] = float(fila["OBS_VALUE"])
                    except (KeyError, TypeError, ValueError):
                        pass
                    filas.append(fila)
            filas.sort(key=lambda f: str(f.get("TIME_PERIOD")))
            guardar(f"serie_{clave}_{fuente}_{area}", filas)
            for f in filas[:2] + filas[-3:]:
                print("  ", f.get("TIME_PERIOD"), f.get("OBS_VALUE"))
            return
    print(f"No se encontraron datos para la clave {clave}. Prueba con `buscar` para encontrar otra.")


def _leer_catalogos():
    for ar in sorted(CARPETA.glob("catalogo_*.csv")):
        with open(ar, encoding="utf-8-sig", newline="") as fh:
            yield ar.stem.replace("catalogo_", ""), list(csv.DictReader(fh))


def cmd_ver():
    """Muestra columnas y primeras filas para entender cómo viene el catálogo."""
    hay = False
    for fuente, filas in _leer_catalogos():
        hay = True
        print(f"\n{fuente}: {len(filas)} filas. Columnas: {list(filas[0].keys()) if filas else []}")
        for f in filas[:5]:
            print("  ", dict(f))
    if not hay:
        sys.exit("Primero descarga el catálogo:  python descargador_inegi.py catalogo")


def cmd_clave(clave):
    """Muestra qué nombre tiene una clave en cada catálogo."""
    encontrada = False
    for fuente, filas in _leer_catalogos():
        for f in filas:
            if clave in [str(v).strip() for v in f.values()]:
                encontrada = True
                print(fuente, "|", dict(f))
    if not encontrada:
        print(f"La clave {clave} no aparece en el catálogo descargado.")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == "ver":
        cmd_ver()
    elif args[0] == "clave" and len(args) > 1:
        cmd_clave(args[1])
    elif args[0] == "catalogo":
        cmd_catalogo()
    elif args[0] == "buscar" and len(args) > 1:
        cmd_buscar(" ".join(args[1:]))
    elif args[0] == "serie" and len(args) > 1:
        fuentes = (args[2].upper(),) if len(args) > 2 else FUENTES
        areas = (args[3],) if len(args) > 3 else AREAS
        cmd_serie(args[1], fuentes, areas)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
