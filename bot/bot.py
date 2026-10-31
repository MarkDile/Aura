"""Aura Coach - bot Telegram (versione 3: comandi /fatto, /oggi, /stato).

Gira su GitHub Actions ogni 30 minuti. A ogni giro:
  1. legge i messaggi nuovi arrivati al bot (getUpdates, con offset salvato);
  2. risponde ai comandi, solo se arrivano dalla tua chat (TELEGRAM_CHAT_ID):
       /fatto <nota>  spunta l'azione del giorno con la data di oggi e la nota
       /oggi          rimanda l'azione del giorno
       /stato         riassume a che punto sei
       /annulla       toglie la spunta all'ultima azione segnata da Telegram
       /aiuto         elenco dei comandi
  3. dalle 7:30 (ora di Roma) manda l'azione del giorno, una volta sola al giorno.
Le modifiche finiscono in bot/azioni.json e bot/stato_bot.json; il workflow
le salva nel repository con un commit.

Token e chat id arrivano dai segreti del repository (TELEGRAM_TOKEN,
TELEGRAM_CHAT_ID) e non vengono mai scritti nei file. Solo libreria standard.
"""
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

VERSIONE = 3
ROMA = ZoneInfo("Europe/Rome")
ORA_INVIO = time(7, 30)
CARTELLA = Path(__file__).parent
FILE_AZIONI = CARTELLA / "azioni.json"
FILE_STATO = CARTELLA / "stato_bot.json"
PAGINA = "https://claude.ai/artifact/MCSMjePnvLRa1EUpvG6wbG"
MAX_NOTA = 1000

TRAGUARDI = {
    0: "9 pinch su 10, circa 30 fps, video della demo «Pianeta sul palmo» da 60 secondi",
    1: "10 persone completano la demo senza istruzioni, errore sotto 1 cm a 40 cm",
    2: "aptico sotto 30 ms, una giornata di batteria, 8 tester su 10 lo preferiscono",
    3: "10 minuti d'uso senza fastidio",
    4: "CE ottenuta, collaudo sopra il 95%, resi sotto il 5%",
}

AIUTO = (
    "<b>Comandi di Aura Coach</b>\n"
    "/fatto <i>nota</i> · spunta l'azione di oggi; la nota è facoltativa "
    "(es. <code>/fatto 22 fps sul Samsung</code>)\n"
    "/oggi · l'azione del giorno\n"
    "/stato · a che punto sei\n"
    "/annulla · toglie l'ultima spunta fatta da qui\n\n"
    "Rispondo entro mezz'ora. Le note finiscono nel repository pubblico: "
    "niente dati personali."
)

e = lambda s: html.escape(str(s or ""), quote=False)


def num(n):
    """7.0 -> '7', 9.5 -> '9.5'"""
    return str(int(n)) if float(n).is_integer() else str(n)


def gg_mm(iso):
    return f"{iso[8:10]}/{iso[5:7]}" if iso else "—"


# ---------- dati ----------

def leggi_json(percorso, predefinito):
    try:
        return json.loads(percorso.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return predefinito


def scrivi_json(percorso, dati):
    testo = json.dumps(dati, ensure_ascii=False, indent=2) + "\n"
    if not percorso.exists() or percorso.read_text(encoding="utf-8") != testo:
        percorso.write_text(testo, encoding="utf-8")


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


# ---------- messaggi ----------

def componi(azioni, oggi):
    per_n = {a["n"]: a for a in azioni}
    fatte = [a for a in azioni if a.get("fatto")]
    a = azione_del_giorno(azioni)
    if a is None:
        return "Aura: tutte le azioni sono fatte! Chiedi a Claude di aggiungerne di nuove."

    righe = [f"🔹 Aura · azione {num(a['n'])} di {len(azioni)} (Fase {a.get('fase', '?')})"]

    if fatte:
        ultima = max(fatte, key=lambda x: (x.get("fattoIl") or "", x["n"]))
        quando = ultima.get("fattoIl")
        testo = e(ultima.get("risultato") or ultima.get("titolo"))
        if quando:
            giorni = (oggi - date.fromisoformat(quando)).days
            if giorni <= 1:
                righe.append(f"Ieri: {testo}" if giorni == 1 else f"Ultima fatta: {testo} (oggi)")
            else:
                righe.append(f"Ultima fatta: {testo} (il {gg_mm(quando)})")
                if giorni >= 7:
                    righe.append("Si riparte da qui: oggi bastano 5 minuti.")
        else:
            righe.append(f"Ultima fatta: {testo}")

    righe.append("")
    righe.append(f"<b>{e(a.get('titolo'))}</b>")
    base = per_n.get(a.get("base"))
    if base:
        righe.append(f"Parte da: {e(base.get('risultato') or base.get('titolo'))}")
    righe.append("")
    righe.append(e(a.get("dettaglio")))
    righe.append("")
    righe.append(f"Fatto quando: {e(a.get('risultato'))}")
    righe.append("Quando hai finito: <code>/fatto</code> e cosa hai visto (numeri, problemi).")
    righe.append("")
    righe.append(f'Stato, appunti e diario: <a href="{PAGINA}">Aura · 10 minuti</a>')
    return "\n".join(righe)


def riepilogo(azioni, oggi):
    fatte = sorted((a for a in azioni if a.get("fatto")),
                   key=lambda x: (x.get("fattoIl") or "", x["n"]))
    prossima = azione_del_giorno(azioni)
    fase = prossima.get("fase", 0) if prossima else max((a.get("fase", 0) for a in azioni), default=0)
    nella_fase = [a for a in azioni if a.get("fase") == fase]
    fatte_fase = sum(1 for a in nella_fase if a.get("fatto"))
    settimana = sum(1 for a in fatte if a.get("fattoIl")
                    and (oggi - date.fromisoformat(a["fattoIl"])).days < 7)

    righe = [
        "📊 <b>Aura · a che punto sei</b>",
        f"Fatte {len(fatte)} di {len(azioni)} · Fase {fase}: {fatte_fase} di {len(nella_fase)}",
        f"Ultimi 7 giorni: {settimana} azioni",
        "",
        "<b>Ultime fatte</b>",
    ]
    for a in fatte[-3:][::-1]:
        riga = f"• {gg_mm(a.get('fattoIl'))} · {e(a.get('risultato') or a.get('titolo'))}"
        if a.get("nota"):
            nota = a["nota"].replace("\n", " ")
            riga += f" — <i>{e(nota[:80])}{'…' if len(nota) > 80 else ''}</i>"
        righe.append(riga)
    if not fatte:
        righe.append("• nessuna ancora")
    righe.append("")
    if prossima:
        righe.append(f"Prossima: <b>{num(prossima['n'])} · {e(prossima.get('titolo'))}</b>")
    righe.append(f"Traguardo della fase: {e(TRAGUARDI.get(fase, '—'))}")
    return "\n".join(righe)


# ---------- comandi ----------

def comando(testo):
    """'/fatto@AuraBot 22 fps' -> ('/fatto', '22 fps')"""
    testo = (testo or "").strip()
    if not testo.startswith("/"):
        return None, testo
    parti = testo.split(maxsplit=1)
    nome = parti[0].split("@")[0].lower()
    return nome, (parti[1].strip() if len(parti) > 1 else "")


def esegui(nome, argomento, azioni, stato, oggi):
    """Esegue un comando, aggiorna azioni/stato in memoria e restituisce la risposta."""
    if nome == "/fatto":
        a = azione_del_giorno(azioni)
        if a is None:
            return "Non c'è nessuna azione da spuntare: sono tutte fatte."
        a["fatto"] = True
        a["fattoIl"] = oggi.isoformat()
        nota = argomento[:MAX_NOTA]
        if nota:
            a["nota"] = (a["nota"] + "\n" + nota) if a.get("nota") else nota
        stato["ultimaSpunta"] = {"id": a["id"], "nota": nota}
        risposta = [f"✅ Fatta: <b>{num(a['n'])} · {e(a.get('titolo'))}</b>"]
        if nota:
            risposta.append(f"Nota salvata: <i>{e(nota)}</i>")
        dopo = azione_del_giorno(azioni)
        if dopo:
            risposta += ["", f"Prossima: <b>{num(dopo['n'])} · {e(dopo.get('titolo'))}</b>",
                         "Se hai ancora tempo: /oggi"]
        return "\n".join(risposta)

    if nome == "/annulla":
        ultima = stato.get("ultimaSpunta")
        a = next((x for x in azioni if ultima and x.get("id") == ultima.get("id")), None)
        if not a or not a.get("fatto"):
            return "Non c'è nessuna spunta da annullare."
        a["fatto"] = False
        a["fattoIl"] = None
        nota = ultima.get("nota") or ""
        if nota and a.get("nota"):
            if a["nota"] == nota:
                a.pop("nota")
            elif a["nota"].endswith("\n" + nota):
                a["nota"] = a["nota"][: -len(nota) - 1]
        stato.pop("ultimaSpunta", None)
        return f"↩️ Tolta la spunta a <b>{num(a['n'])} · {e(a.get('titolo'))}</b>."

    if nome == "/oggi":
        return componi(azioni, oggi)
    if nome == "/stato":
        return riepilogo(azioni, oggi)
    return AIUTO  # /aiuto, /start, /help e qualsiasi altro testo


# ---------- Telegram ----------

def chiama(token, metodo, parametri):
    url = f"https://api.telegram.org/bot{token}/{metodo}"
    dati = urllib.parse.urlencode(parametri).encode()
    try:
        with urllib.request.urlopen(url, data=dati, timeout=30) as r:
            risposta = json.load(r)
    except urllib.error.HTTPError as err:
        raise SystemExit(f"Telegram ha risposto {err.code} a {metodo}: "
                         f"{err.read().decode(errors='replace')}")
    if not risposta.get("ok"):
        raise SystemExit(f"Telegram: {metodo} non riuscito: {risposta}")
    return risposta["result"]


def invia(token, chat_id, testo):
    return chiama(token, "sendMessage", {
        "chat_id": chat_id, "text": testo,
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    })


# ---------- giro ----------

def giro(token, chat_id, adesso, prova=False):
    oggi = adesso.date()
    dati = leggi_json(FILE_AZIONI, {"azioni": []})
    azioni = dati["azioni"] if isinstance(dati, dict) else dati
    stato = leggi_json(FILE_STATO, {})
    uscita = []  # messaggi da mandare

    # 1. messaggi nuovi
    aggiornamenti = chiama(token, "getUpdates", {
        "offset": stato.get("offset", 0), "timeout": 0,
        "allowed_updates": json.dumps(["message"]),
    })
    for u in aggiornamenti:
        stato["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != str(chat_id):
            continue  # risponde solo alla tua chat
        nome, argomento = comando(msg.get("text"))
        uscita.append(esegui(nome, argomento, azioni, stato, oggi))

    # 2. l'azione del giorno, dalle 7:30 una volta al giorno
    if adesso.time() >= ORA_INVIO and stato.get("ultimoInvio") != oggi.isoformat():
        uscita.append(componi(azioni, oggi))
        stato["ultimoInvio"] = oggi.isoformat()

    for testo in uscita:
        if prova:
            print("---\n" + testo)
        else:
            invia(token, chat_id, testo)

    stato["versione"] = VERSIONE
    if isinstance(dati, dict):
        dati["azioni"] = azioni
    scrivi_json(FILE_AZIONI, dati)
    scrivi_json(FILE_STATO, stato)
    print(f"Giro completato: {len(aggiornamenti)} messaggi letti, {len(uscita)} inviati.")


def main():
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    mancano = [n for n, v in (("TELEGRAM_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)) if not v]
    if mancano:
        sys.exit("Segreti mancanti: " + ", ".join(mancano))
    giro(token, chat_id, datetime.now(ROMA), prova=os.environ.get("PROVA") == "1")


if __name__ == "__main__":
    main()
