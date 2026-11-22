import json
import os
import requests
import tweepy
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("X_API_KEY")
API_SECRET = os.getenv("X_API_SECRET")
ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_ULTIMO = os.path.join(BASE_DIR, "ultimo_dato.json")


def cargar_ultimo():
    if os.path.exists(ARCHIVO_ULTIMO):
        with open(ARCHIVO_ULTIMO, "r") as f:
            return json.load(f)
    return {}


def guardar_ultimo(datos):
    with open(ARCHIVO_ULTIMO, "w") as f:
        json.dump(datos, f)


def flecha(actual, anterior):
    if anterior is None:
        return ""
    if actual > anterior:
        return " 🔼"
    if actual < anterior:
        return " 🔽"
    return ""


def obtener_dolar(ultimo):
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/oficial", timeout=10)
        r.raise_for_status()
        data = r.json()
        compra, venta = data["compra"], data["venta"]
        clave = f"{compra}-{venta}"
        if ultimo.get("dolar") == clave:
            return None, {}
        texto = f"💵 Dólar Oficial: Compra ${compra} / Venta ${venta}{flecha(venta, ultimo.get('dolar_venta'))}"
        return texto, {"dolar": clave, "dolar_venta": venta}
    except Exception as e:
        print(f"Error dólar: {e}")
        return None, {}


def obtener_riesgo_pais(ultimo):
    try:
        r = requests.get(
            "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais/ultimo",
            timeout=10,
        )
        r.raise_for_status()
        valor = r.json()["valor"]
        if ultimo.get("riesgo") == valor:
            return None, {}
        texto = f"📊 Riesgo País: {valor} puntos{flecha(valor, ultimo.get('riesgo'))}"
        return texto, {"riesgo": valor}
    except Exception as e:
        print(f"Error riesgo país: {e}")
        return None, {}


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
        return False


if __name__ == "__main__":
    ultimo = cargar_ultimo()
    lineas = []
    nuevos = {}

    for obtener in (obtener_dolar, obtener_riesgo_pais):
        texto, datos = obtener(ultimo)
        if texto:
            lineas.append(texto)
            nuevos.update(datos)

    if lineas:
        texto_final = "\n".join(lineas)
        print("Publicando:\n" + texto_final)
        if publicar_tweet(texto_final):
            ultimo.update(nuevos)
            guardar_ultimo(ultimo)
    else:
        print("Sin cambios. No se publica (ahorro de costo).")