"""Aura Coach - bot Telegram (versione 1: primo messaggio).

Gira su GitHub Actions. Legge token e chat id dai segreti del repository
(variabili d'ambiente TELEGRAM_TOKEN e TELEGRAM_CHAT_ID): nel codice non
c'e' nessuna chiave. Usa solo la libreria standard di Python.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VERSIONE = 1


def invia(token: str, chat_id: str, testo: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    dati = urllib.parse.urlencode({"chat_id": chat_id, "text": testo}).encode()
    try:
        with urllib.request.urlopen(url, data=dati, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # Telegram spiega l'errore nel corpo della risposta (senza mostrare il token)
        corpo = e.read().decode(errors="replace")
        raise SystemExit(f"Telegram ha risposto {e.code}: {corpo}")


def main() -> None:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    mancano = [n for n, v in (("TELEGRAM_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)) if not v]
    if mancano:
        sys.exit("Segreti mancanti: " + ", ".join(mancano)
                 + ". Controlla Settings > Secrets and variables > Actions.")

    ora = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    testo = (
        "Ciao Marco, sono Aura Coach.\n"
        "Se leggi questo messaggio, GitHub Actions e Telegram sono collegati.\n"
        f"Inviato il {ora} (bot versione {VERSIONE})."
    )
    risposta = invia(token, chat_id, testo)
    if not risposta.get("ok"):
        sys.exit(f"Invio non riuscito: {risposta}")
    print("Messaggio inviato, id", risposta["result"]["message_id"])


if __name__ == "__main__":
    main()
