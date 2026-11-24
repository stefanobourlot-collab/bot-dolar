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
        raise SystemExit(1)