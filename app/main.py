import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from sqlalchemy import select

from . import config, whatsapp
from .agent import responder
from .db import Base, SessionLocal, engine
from .models import Cliente, Conversa, Mensagem, Tenant

log = logging.getLogger("estetica")


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)  # simples por enquanto; Alembic quando o schema estabilizar
    yield


app = FastAPI(title="Estética SaaS", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/webhook/evolution")
async def webhook(request: Request, bg: BackgroundTasks, token: str = ""):
    """Configure na Evolution: URL .../webhook/evolution?token=SEU_SEGREDO, evento MESSAGES_UPSERT."""
    if not secrets.compare_digest(token, config.WEBHOOK_SECRET):
        raise HTTPException(401)
    msg = whatsapp.extrair_mensagem(await request.json())
    if msg:
        bg.add_task(processar, msg)
    return {"ok": True}


def processar(msg: dict) -> None:
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(
            Tenant.instancia == msg["instancia"], Tenant.ativo.is_(True)))
        if not tenant:
            return
        if msg["wa_id"] and db.scalar(select(Mensagem.id).join(Conversa).where(
                Conversa.tenant_id == tenant.id, Mensagem.wa_id == msg["wa_id"])):
            return  # webhook repetido

        cliente = db.scalar(select(Cliente).where(
            Cliente.tenant_id == tenant.id, Cliente.telefone == msg["telefone"]))
        if not cliente:
            cliente = Cliente(tenant_id=tenant.id, telefone=msg["telefone"], nome=msg["nome"])
            db.add(cliente)
            db.flush()
        conversa = db.scalar(select(Conversa).where(
            Conversa.tenant_id == tenant.id, Conversa.cliente_id == cliente.id))
        if not conversa:
            conversa = Conversa(tenant_id=tenant.id, cliente_id=cliente.id)
            db.add(conversa)
            db.flush()

        db.add(Mensagem(conversa_id=conversa.id, papel="cliente",
                        texto=msg["texto"], wa_id=msg["wa_id"]))
        conversa.atualizada_em = config.agora()
        db.commit()
        if conversa.humano:  # equipe assumiu: a IA fica quieta
            return

        try:
            resposta = responder(db, tenant, conversa, cliente)
        except Exception:
            log.exception("falha ao gerar resposta")
            db.rollback()
            resposta = "Opa, tive um probleminha aqui. Pode me mandar de novo daqui a pouquinho?"
        db.add(Mensagem(conversa_id=conversa.id, papel="ia", texto=resposta))
        db.commit()
        try:
            whatsapp.enviar_texto(tenant.instancia, msg["telefone"], resposta)
        except Exception:
            log.exception("falha ao enviar pelo WhatsApp")
