"""Aura Coach - bot Telegram (versione 2: l'azione del giorno).

Gira su GitHub Actions. Legge bot/azioni.json, sceglie l'azione del giorno
(n piu' basso tra le non fatte, risalendo alle basi non fatte) e la manda su
Telegram. Token e chat id arrivano dai segreti del repository
(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID). Solo libreria standard di Python.
"""
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VERSIONE = 2
ROMA = ZoneInfo("Europe/Rome")
FILE_AZIONI = Path(__file__).with_name("azioni.json")
PAGINA = "https://claude.ai/artifact/MCSMjePnvLRa1EUpvG6wbG"


def num(n):
    """7.0 -> '7', 9.5 -> '9.5'"""
    return str(int(n)) if float(n).is_integer() else str(n)


def azione_del_giorno(azioni):
    per_n = {a["n"]: a for a in azioni}
    da_fare = [a for a in azioni if not a.get("fatto")]
    if not da_fare:
        return None
    a = min(da_fare, key=lambda x: x["n"])
    visti = set()
    # se la base non e' fatta, l'azione del giorno diventa la base
    while a.get("base") is not None and a["base"] in per_n and not per_n[a["base"]].get("fatto"):
        if a["n"] in visti:
            break  # catena circolare: ci fermiamo
        visti.add(a["n"])
        a = per_n[a["base"]]
    return a


def componi(azioni, oggi):
    per_n = {a["n"]: a for a in azioni}
    fatte = [a for a in azioni if a.get("fatto")]
    a = azione_del_giorno(azioni)
    e = lambda s: html.escape(s, quote=False)
    if a is None:
        return "Aura: tutte le azioni sono fatte! Chiedi a Claude di aggiungerne di nuove."

    righe = [f"🔹 Aura · azione {num(a['n'])} di {len(azioni)} (Fase {a.get('fase', '?')})"]

    if fatte:
        ultima = max(fatte, key=lambda x: (x.get("fattoIl") or "", x["n"]))
        quando = ultima.get("fattoIl")
        testo = e(ultima.get("risultato") or ultima.get("titolo", ""))
        if quando:
            giorni = (oggi - date.fromisoformat(quando)).days
            if giorni <= 1:
                righe.append(f"Ieri: {testo}" if giorni == 1 else f"Ultima fatta: {testo} (oggi)")
            else:
                righe.append(f"Ultima fatta: {testo} (il {quando[8:10]}/{quando[5:7]})")
                if giorni >= 7:
                    righe.append("Si riparte da qui: oggi bastano 5 minuti.")
        else:
            righe.append(f"Ultima fatta: {testo}")

    righe.append("")
    righe.append(f"<b>{e(a.get('titolo', ''))}</b>")
    base = per_n.get(a.get("base"))
    if base:
        righe.append(f"Parte da: {e(base.get('risultato') or base.get('titolo', ''))}")
    righe.append("")
    righe.append(e(a.get("dettaglio", "")))
    righe.append("")
    righe.append(f"Fatto quando: {e(a.get('risultato', ''))}")
    righe.append("Quando hai finito, spunta e scrivi nella nota cosa hai visto (numeri, problemi).")
    righe.append("")
    righe.append(f'Stato, appunti e diario: <a href="{PAGINA}">Aura · 10 minuti</a>')
    return "\n".join(righe)


def invia(token, chat_id, testo):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    dati = urllib.parse.urlencode({
        "chat_id": chat_id, "text": testo,
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(url, data=dati, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as err:
        raise SystemExit(f"Telegram ha risposto {err.code}: {err.read().decode(errors='replace')}")


def ora_giusta():
    """Il workflow parte alle 5:30 e alle 6:30 UTC: invia solo quella che a Roma sono le 7:30.
    Cosi' funziona sia con l'ora legale sia con quella solare, anche se GitHub parte in ritardo."""
    cron = os.environ.get("CRON", "").strip()
    if not cron:
        return True  # avvio a mano: invia sempre
    offset_ore = datetime.now(ROMA).utcoffset().total_seconds() / 3600
    voluto = "30 5 * * *" if offset_ore == 2 else "30 6 * * *"
    return cron == voluto


def main():
    if not ora_giusta():
        print("Non e' questo l'orario giusto per Roma: salto.")
        return
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    mancano = [n for n, v in (("TELEGRAM_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)) if not v]
    if mancano:
        sys.exit("Segreti mancanti: " + ", ".join(mancano))
    dati = json.loads(FILE_AZIONI.read_text(encoding="utf-8"))
    azioni = dati["azioni"] if isinstance(dati, dict) else dati
    testo = componi(azioni, datetime.now(ROMA).date())
    if os.environ.get("PROVA") == "1":
        print(testo)
        return
    r = invia(token, chat_id, testo)
    if not r.get("ok"):
        sys.exit(f"Invio non riuscito: {r}")
    print("Messaggio inviato, id", r["result"]["message_id"])


if __name__ == "__main__":
    main()
