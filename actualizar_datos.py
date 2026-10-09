"""Actualiza data/datos.json con los indicadores definidos en INDICADORES, abajo.

Jala las series directo de la API del INEGI. No requiere descargar nada a mano.

Uso normal (pide el token, no lo guarda):
  python actualizar_datos.py

Si prefieres no escribir el token cada vez, en Windows PowerShell:
  $env:INEGI_TOKEN = "tu-token"
  python actualizar_datos.py

Para agregar un indicador nuevo: añade una entrada a INDICADORES con su(s)
clave(s), confirmadas antes en el Constructor de consultas del INEGI y
verificadas con el descargador_inegi.py contra un boletín real.
"""
import getpass
import json
import os
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

FUENTE = "BIE-BISE"   # catálogo unificado del INEGI desde el 1-dic-2025
AREA = "00"           # nacional

# Cada indicador puede traer solo "original", o "original" + "desestacionalizada".
# Las claves deben estar confirmadas contra un boletín del INEGI antes de agregarlas aquí.
INDICADORES = {
    "inflacion": {
        "claves": {"original": "910406"},   # INPC. Inflación anual
        "decimales": 2,
    },
    "desocupacion": {
        "claves": {
            "original": "444603",            # Tasa de desocupación
            "desestacionalizada": "444884",  # Tasa de desocupación, serie desestacionalizada (índice)
        },
        "decimales": 1,
    },
}


def pedir_api(claves, token):
    """Pide una o varias claves (separadas por coma) a la API y regresa
    {clave: {mes: valor}} con todas las que haya podido traer."""
    url = ("https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/"
           f"INDICATOR/{claves}/es/{AREA}/false/{FUENTE}/2.0/{token}?type=json")
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            datos = json.loads(r.read().decode("utf-8-sig"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace").replace(token, "***")[:300]
        print(f"   La API respondió con error {e.code}: {cuerpo}")
        return {}
    except Exception as e:
        print(f"   No se pudo conectar a la API: {type(e).__name__}")
        return {}

    series = datos.get("Series") if isinstance(datos, dict) else None
    if not series:
        print("   La API respondió, pero sin series:", json.dumps(datos, ensure_ascii=False)[:300])
        return {}

    por_clave = {}
    for s in series:
        clave = s.get("INDICADOR")
        pares = {}
        for o in s.get("OBSERVATIONS", []):
            if o.get("OBS_VALUE") not in (None, ""):
                pares[o["TIME_PERIOD"].replace("/", "-")] = round(float(o["OBS_VALUE"]), 2)
        por_clave[clave] = pares
    return por_clave


def guardar(nombre_archivo, salida):
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nListo: {SALIDA}")


def main():
    token = os.environ.get("INEGI_TOKEN") or getpass.getpass("Token del INEGI: ").strip()

    # Trae TODAS las claves de todos los indicadores en una sola llamada a la API
    # (la API acepta varias claves separadas por coma), y luego las reparte.
    todas_las_claves = [clave for ind in INDICADORES.values() for clave in ind["claves"].values()]
    print(f"Consultando {len(todas_las_claves)} clave(s) en la API del INEGI...")
    valores_por_clave = pedir_api(",".join(todas_las_claves), token)

    salida_final = {}
    for nombre, config in INDICADORES.items():
        decimales = config.get("decimales", 2)
        pares_por_tipo = {}
        for tipo, clave in config["claves"].items():
            pares = valores_por_clave.get(clave)
            if not pares:
                print(f"AVISO: '{nombre}' ({tipo}, clave {clave}) no trajo datos. Se deja tal como estaba.")
                continue
            pares_por_tipo[tipo] = pares

        if not pares_por_tipo:
            continue  # nada que actualizar para este indicador

        # Eje de meses común: la UNIÓN de fechas de todas las series de este
        # indicador, para que original y desestacionalizada queden alineadas
        # punto a punto aunque una empiece antes que la otra.
        todos_los_meses = sorted(set().union(*pares_por_tipo.values()))[-MESES_A_MOSTRAR:]

        resultado = {"meses": todos_los_meses}
        for tipo, pares in pares_por_tipo.items():
            clave_salida = "serie" if tipo == "original" else f"serie_{tipo}"
            resultado[clave_salida] = [pares.get(m) for m in todos_los_meses]  # None donde falte el dato

        anio, mes = resultado["meses"][-1].split("-")
        resultado["decimales"] = decimales
        resultado["corte"] = f"{NOMBRES[int(mes) - 1]} {anio}"
        resultado["actualizado"] = datetime.now().strftime("%Y-%m-%d")
        salida_final[nombre] = resultado

        print(f"\n{nombre}: {len(resultado['meses'])} meses. Últimos valores:")
        for m in resultado["meses"][-3:]:
            i = resultado["meses"].index(m)
            linea = f"  {m}: original={resultado.get('serie', [None]*len(resultado['meses']))[i]}"
            if "serie_desestacionalizada" in resultado:
                linea += f"  desestacionalizada={resultado['serie_desestacionalizada'][i]}"
            print(linea)

    if not salida_final:
        sys.exit("\nNo se obtuvo ningún dato nuevo. No se modificó data/datos.json.")

    # No borra indicadores que ya existían en el archivo y que esta corrida no trajo
    if SALIDA.exists():
        anterior = json.loads(SALIDA.read_text(encoding="utf-8"))
        anterior.update(salida_final)
        salida_final = anterior

    guardar(SALIDA, salida_final)


if __name__ == "__main__":
    main()
