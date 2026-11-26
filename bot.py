import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import tweepy
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("X_API_KEY")
API_SECRET = os.getenv("X_API_SECRET")
ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_ESTADO = os.path.join(BASE_DIR, "ultimo_dato.json")

# ======================= CONFIGURACIÓN =======================
# clave que usa dolarapi.com : (emoji, nombre que se muestra)
# Otras disponibles: "mayorista", "tarjeta" (ojo con el límite de 280 caracteres)
CASAS = {
    "oficial": ("🏦", "Oficial"),
    "blue": ("💙", "Blue"),
    "bolsa": ("📈", "MEP"),
    "contadoconliqui": ("🌐", "CCL"),
    "cripto": ("🪙", "Cripto"),
}
RIESGO = ("📊", "Riesgo país")

HASHTAGS_HORARIO = "#Dólar #DólarBlue"          # tweet horario ("" para no poner)
HASHTAGS_RESUMEN = "#Dólar #DólarBlue #RiesgoPaís"  # resumen de cierre

# El riesgo país de argentinadatos se actualiza con retraso (suele traer el cierre
# del día anterior). Con True, solo se publica si el dato es de HOY.
RIESGO_SOLO_SI_ES_DE_HOY = True

UMBRAL_PCT = 0.5               # variación mínima (%) para mostrar flecha y publicar
MIN_HORAS_ENTRE_TWEETS = 2     # separación mínima entre tweets "normales"
HORA_RESUMEN = 19              # hora argentina del resumen de cierre
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
# =============================================================

ORDEN = list(CASAS) + ["riesgo"]


# ---------- estado ----------
def cargar_estado():
    if os.path.exists(ARCHIVO_ESTADO):
        try:
            with open(ARCHIVO_ESTADO, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"No se pudo leer el estado: {e}")
    return {}


def guardar_estado(estado):
    with open(ARCHIVO_ESTADO, "w") as f:
        json.dump(estado, f, indent=2)


# ---------- datos ----------
def a_numero(texto):
    """Convierte '1.094,50' / '1094.5' / 1094 en float."""
    t = str(texto).strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") == 1 and len(t.split(".")[1]) == 3:
        t = t.replace(".", "")
    return float(t)


def riesgo_ambito():
    """Riesgo país en vivo (Ámbito, API no oficial). Devuelve None si falla."""
    try:
        r = requests.get(
            "https://mercados.ambito.com//riesgopais/variacion",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        print(f"Riesgo país Ámbito (respuesta): {str(data)[:200]}")
        return a_numero(data.get("ultimo", data.get("valor")))
    except Exception as e:
        print(f"Riesgo país Ámbito falló: {e}")
        return None


def riesgo_argentinadatos():
    """Respaldo: solo se usa si el dato es de hoy (suele venir con 1 día de atraso)."""
    try:
        r = requests.get(
            "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais/ultimo",
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        fecha = str(data.get("fecha", ""))[:10]
        if RIESGO_SOLO_SI_ES_DE_HOY and fecha != datetime.now(TZ).date().isoformat():
            print(f"Riesgo país desactualizado (dato del {fecha}). Se omite.")
            return None
        return float(data["valor"])
    except Exception as e:
        print(f"Error riesgo país: {e}")
        return None


def obtener_precios():
    precios = {}
    try:
        r = requests.get("https://dolarapi.com/v1/dolares", timeout=10)
        r.raise_for_status()
        for d in r.json():
            if d.get("casa") in CASAS and d.get("venta"):
                precios[d["casa"]] = float(d["venta"])
    except Exception as e:
        print(f"Error dólares: {e}")

    for clave in CASAS:
        if clave not in precios:
            print(f"Aviso: no llegó la cotización de '{clave}'")

    riesgo = riesgo_ambito() or riesgo_argentinadatos()
    if riesgo is not None:
        precios["riesgo"] = riesgo
    return precios


# ---------- formato ----------
def etiqueta(clave):
    emoji, nombre = RIESGO if clave == "riesgo" else CASAS[clave]
    return f"{emoji} {nombre}"


def fmt_valor(clave, v):
    if clave == "riesgo":
        return f"{v:.0f} pts"
    return "$" + f"{v:,.0f}".replace(",", ".")


def variacion_pct(actual, base):
    return (actual - base) / base * 100


def fmt_pct(p):
    return f"{p:+.2f}%".replace(".", ",")


def flecha(p):
    return "🔼" if p > 0 else "🔽"


def agregar_hashtags(texto, hashtags):
    return f"{texto}\n\n{hashtags}" if hashtags else texto


def tweet_horario(precios, publicado):
    """Todos los precios; flecha solo en los que se movieron más que el umbral."""
    lineas = ["💱 Cotizaciones"]
    hay_cambio = not publicado  # primer tweet: publica como base
    for clave in ORDEN:
        if clave not in precios:
            continue
        linea = f"{etiqueta(clave)}: {fmt_valor(clave, precios[clave])}"
        base = publicado.get(clave)
        if base:
            p = variacion_pct(precios[clave], base)
            if abs(p) >= UMBRAL_PCT:
                linea += f" {flecha(p)}"
                hay_cambio = True
        lineas.append(linea)
    return agregar_hashtags("\n".join(lineas), HASHTAGS_HORARIO), hay_cambio


def tweet_resumen(precios, cierre):
    """Resumen del día: variación en % contra el cierre anterior."""
    lineas = ["🔔 Cierre del día"]
    hay_variacion = False
    for clave in ORDEN:
        if clave not in precios:
            continue
        linea = f"{etiqueta(clave)}: {fmt_valor(clave, precios[clave])}"
        base = cierre.get(clave)
        if base:
            p = variacion_pct(precios[clave], base)
            if round(p, 2) != 0:
                hay_variacion = True
                linea += f" {flecha(p)} {fmt_pct(p)}"
            else:
                linea += " ➖ 0,00%"
        lineas.append(linea)
    return agregar_hashtags("\n".join(lineas), HASHTAGS_RESUMEN), hay_variacion


# ---------- X ----------
def publicar_tweet(texto):
    try:
        client = tweepy.Client(
            consumer_key=API_KEY,
            consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_SECRET,
        )
        response = client.create_tweet(text=texto)
        print(f"✅ Tweet publicado: {response.data['id']}")
        return True
    except Exception as e:
        print(f"❌ Error publicando: {e}")
        respuesta = getattr(e, "response", None)
        if respuesta is not None:
            print(f"Detalle de X (código {respuesta.status_code}): {respuesta.text[:500]}")
        raise SystemExit(1)


# ---------- lógica principal ----------
def main():
    ahora = datetime.now(TZ)
    hoy = ahora.date().isoformat()
    estado = cargar_estado()

    precios = obtener_precios()
    if not any(k in precios for k in CASAS):
        print("No se pudieron obtener cotizaciones. No se publica.")
        return

    publicado = estado.get("publicado", {})

    # 1) Resumen de cierre (una vez por día, desde las HORA_RESUMEN)
    if ahora.hour >= HORA_RESUMEN and estado.get("resumen_fecha") != hoy:
        cierre = estado.get("cierre_anterior") or publicado
        texto, hay = tweet_resumen(precios, cierre)
        if hay:
            print("Publicando resumen:\n" + texto)
            if not publicar_tweet(texto):
                return
            publicado.update(precios)
            estado["publicado"] = publicado
            estado["ultimo_tweet"] = ahora.isoformat()
        else:
            print("Sin variación en el día. No se publica el resumen.")
        base = estado.get("cierre_anterior", {})
        base.update(precios)
        estado["cierre_anterior"] = base
        estado["resumen_fecha"] = hoy
        guardar_estado(estado)
        return

    # 2) Tweet horario: solo si hubo cambios y pasó el tiempo mínimo
    ultimo = estado.get("ultimo_tweet")
    if ultimo:
        horas = (ahora - datetime.fromisoformat(ultimo)).total_seconds() / 3600
        if horas < MIN_HORAS_ENTRE_TWEETS - 0.25:
            print(f"Último tweet hace {horas:.1f} h. Se espera. No se publica.")
            return

    texto, hay = tweet_horario(precios, publicado)
    if not hay:
        print("Sin cambios relevantes. No se publica (ahorro de costo).")
        return

    print("Publicando:\n" + texto)
    if publicar_tweet(texto):
        publicado.update(precios)
        estado["publicado"] = publicado
        estado["ultimo_tweet"] = ahora.isoformat()
        guardar_estado(estado)


if __name__ == "__main__":
    main()