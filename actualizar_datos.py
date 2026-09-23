"""Actualiza data/datos.json con la inflación anual del INEGI.

Método principal: la API del INEGI (clave 910406, "INPC. Inflación anual",
fuente BIE-BISE). No requiere descargar nada a mano.

Uso normal (pide el token, no lo guarda):
  python actualizar_datos.py

Si prefieres no escribir el token cada vez, en Windows PowerShell:
  $env:INEGI_TOKEN = "tu-token"
  python actualizar_datos.py

Respaldo sin API: si tienes un CSV descargado del INEGI (el mismo formato que
usamos antes) en esta carpeta o en data/, puedes forzar su uso con:
  python actualizar_datos.py --csv
"""
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

CARPETA = Path(__file__).parent
SALIDA = CARPETA / "data" / "datos.json"
MESES_A_MOSTRAR = 120
NOMBRES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

CLAVE_INFLACION = "910406"   # INPC. Inflación anual (confirmada contra el portal del INEGI)
FUENTE = "BIE-BISE"          # catálogo unificado del INEGI desde el 1-dic-2025
AREA = "00"                  # nacional


# ---------- Método 1: API del INEGI ----------

def desde_api():
    token = os.environ.get("INEGI_TOKEN") or getpass.getpass("Token del INEGI: ").strip()
    url = ("https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/"
           f"INDICATOR/{CLAVE_INFLACION}/es/{AREA}/false/{FUENTE}/2.0/{token}?type=json")
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            datos = json.loads(r.read().decode("utf-8-sig"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace").replace(token, "***")[:300]
        print(f"La API respondió con error {e.code}: {cuerpo}")
        return None
    except Exception as e:
        print(f"No se pudo conectar a la API: {type(e).__name__}")
        return None

    try:
        obs = datos["Series"][0]["OBSERVATIONS"]
    except (KeyError, IndexError, TypeError):
        print("La API respondió, pero sin la serie esperada:", json.dumps(datos, ensure_ascii=False)[:300])
        return None

    pares = [(o["TIME_PERIOD"].replace("/", "-"), float(o["OBS_VALUE"]))
             for o in obs if o.get("OBS_VALUE") not in (None, "")]
    pares.sort()
    if len(pares) < 13:
        print(f"La API devolvió solo {len(pares)} dato(s); se esperaba la serie histórica completa.")
        return None
    return [m for m, _ in pares], [round(v, 2) for _, v in pares]


# ---------- Método 2 (respaldo): CSV descargado a mano ----------

def encontrar_csv():
    candidatos = list(CARPETA.glob("Indicadores*.csv")) + list((CARPETA / "data").glob("Indicadores*.csv"))
    return max(candidatos, key=lambda p: p.stat().st_mtime) if candidatos else None


def desde_csv():
    ruta = encontrar_csv()
    if not ruta:
        sys.exit("No encontré ningún archivo Indicadores*.csv en esta carpeta ni en data/.")
    crudo = ruta.read_bytes()
    texto = None
    for codificacion in ("utf-16", "utf-8-sig", "cp1252"):
        try:
            texto = crudo.decode(codificacion)
            break
        except UnicodeError:
            continue
    if texto is None:
        sys.exit("No pude leer el archivo: codificación desconocida.")

    lineas = texto.splitlines()
    if lineas and "Variación Porcentual" not in lineas[0]:
        print("AVISO: el encabezado no dice 'Variación Porcentual'. Revisa que sea la inflación anual.")

    meses, serie = [], []
    for linea in lineas[1:]:
        campos = linea.split(",")
        if len(campos) >= 3 and re.fullmatch(r"\d{4}/\d{2}", campos[0].strip()) and campos[2].strip():
            meses.append(campos[0].strip().replace("/", "-"))
            serie.append(float(campos[2]))
    if len(serie) < 13:
        sys.exit("El archivo tiene muy pocos datos. ¿Es el CSV correcto?")
    print(f"Archivo leído: {ruta.name}")
    return meses, serie


# ---------- Guardar ----------

def guardar(meses, serie):
    meses, serie = meses[-MESES_A_MOSTRAR:], serie[-MESES_A_MOSTRAR:]
    anio, mes = meses[-1].split("-")
    salida = {"inflacion": {
        "meses": meses,
        "serie": serie,
        "decimales": 2,
        "corte": f"{NOMBRES[int(mes) - 1]} {anio}",
        "actualizado": datetime.now().strftime("%Y-%m-%d"),
    }}
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Listo: {len(serie)} meses guardados en {SALIDA}")
    print("Últimos valores (compáralos con lo que publica el INEGI):")
    for m, v in list(zip(meses, serie))[-3:]:
        print(f"  {m}: {v} %")


def main():
    forzar_csv = "--csv" in sys.argv[1:]
    resultado = None if forzar_csv else desde_api()
    if resultado is None:
        print("Usando el respaldo con archivo CSV..." if not forzar_csv else "Modo --csv solicitado.")
        resultado = desde_csv()
    guardar(*resultado)


if __name__ == "__main__":
    main()
