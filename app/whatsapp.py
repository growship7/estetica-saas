import time

import httpx

from . import config


def enviar_texto(instancia: str, telefone: str, texto: str) -> None:
    """Evolution API v2. Parágrafos viram mensagens separadas, com pausa curta (mais humano)."""
    partes = [p.strip() for p in texto.split("\n\n") if p.strip()][:4] or [texto]
    for i, parte in enumerate(partes):
        if i:
            time.sleep(min(1.0 + len(parte) / 60, 4))
        r = httpx.post(f"{config.EVOLUTION_URL}/message/sendText/{instancia}",
                       headers={"apikey": config.EVOLUTION_API_KEY},
                       json={"number": telefone, "text": parte}, timeout=20)
        r.raise_for_status()


def extrair_mensagem(payload: dict) -> dict | None:
    """Pega só texto recebido de contato individual. Devolve None para o resto."""
    evento = str(payload.get("event", "")).lower().replace("_", ".")
    if evento != "messages.upsert":
        return None
    d = payload.get("data") or {}
    key = d.get("key") or {}
    jid = key.get("remoteJid", "")
    if jid.endswith("@lid"):  # alguns números chegam como LID; o número real vem em outro campo
        jid = key.get("remoteJidAlt") or key.get("senderPn") or jid
    if key.get("fromMe") or not jid.endswith("@s.whatsapp.net"):
        return None
    m = d.get("message") or {}
    texto = m.get("conversation") or (m.get("extendedTextMessage") or {}).get("text")
    if not texto or not texto.strip():
        return None
    return {"instancia": payload.get("instance"), "telefone": jid.split("@")[0],
            "nome": d.get("pushName"), "texto": texto.strip(), "wa_id": key.get("id")}
