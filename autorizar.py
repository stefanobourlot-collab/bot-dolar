import os
import tweepy
from dotenv import load_dotenv

load_dotenv()
auth = tweepy.OAuth1UserHandler(
    os.getenv("X_API_KEY"), os.getenv("X_API_SECRET"), callback="oob"
)
print("Abrí este link en la ventana de incógnito:")
print(auth.get_authorization_url())
pin = input("Pegá el PIN que te muestra X: ")
token, secret = auth.get_access_token(pin)
print("X_ACCESS_TOKEN =", token)
print("X_ACCESS_SECRET =", secret)