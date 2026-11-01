"""API do painel. Toda rota filtra pelo tenant do usuário logado."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from . import auth, whatsapp
from .config import agora
from .models import Agendamento, Cliente, Conversa, Mensagem, Tenant, Usuario

router = APIRouter(prefix="/api")


class Login(BaseModel):
    email: str
    senha: str


class Humano(BaseModel):
    humano: bool


class Texto(BaseModel):
    texto: str


@router.post("/login")
def login(d: Login, request: Request, response: Response, db=Depends(auth.get_db)):
    u = db.scalar(select(Usuario).where(Usuario.email == d.email.strip().lower()))
    if not u or not auth.confere(d.senha, u.senha_hash):
        raise HTTPException(401, "E-mail ou senha incorretos")
    seguro = request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie("sessao", auth.criar_token(u.id), max_age=auth.DURACAO,
                        httponly=True, samesite="lax", secure=seguro)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("sessao")
    return {"ok": True}


@router.get("/me")
def me(u=Depends(auth.usuario_atual), db=Depends(auth.get_db)):
    return {"empresa": db.get(Tenant, u.tenant_id).nome, "email": u.email}


@router.get("/agenda")
def agenda(data: str = "", dias: int = 1, u=Depends(auth.usuario_atual), db=Depends(auth.get_db)):
    try:
        ini = datetime.strptime(data, "%Y-%m-%d") if data else datetime.combine(agora().date(), datetime.min.time())
    except ValueError:
        raise HTTPException(400, "Data inválida")
    fim = ini + timedelta(days=max(1, min(dias, 31)))
    ags = db.scalars(select(Agendamento).where(
        Agendamento.tenant_id == u.tenant_id, Agendamento.inicio >= ini, Agendamento.inicio < fim,
        Agendamento.status != "cancelado").order_by(Agendamento.inicio)).all()
    out = []
    for a in ags:
        c = db.get(Cliente, a.cliente_id)
        out.append({"id": a.id, "inicio": a.inicio.isoformat(), "fim": a.fim.isoformat(),
                    "servico": a.servico.nome, "veiculo": a.veiculo.modelo, "placa": a.veiculo.placa,
                    "cliente": c.nome or c.telefone, "telefone": c.telefone,
                    "preco": float(a.preco or 0), "status": a.status, "origem": a.origem})
    return out


@router.post("/agendamentos/{ag_id}/cancelar")
def cancelar(ag_id: int, u=Depends(auth.usuario_atual), db=Depends(auth.get_db)):
    a = db.scalar(select(Agendamento).where(Agendamento.id == ag_id, Agendamento.tenant_id == u.tenant_id))
    if not a:
        raise HTTPException(404, "Agendamento não encontrado")
    a.status = "cancelado"
    db.commit()
    return {"ok": True}


def _conversa(db, u, conversa_id) -> Conversa:
    c = db.scalar(select(Conversa).where(Conversa.id == conversa_id, Conversa.tenant_id == u.tenant_id))
    if not c:
        raise HTTPException(404, "Conversa não encontrada")
    return c


@router.get("/conversas")
def conversas(u=Depends(auth.usuario_atual), db=Depends(auth.get_db)):
    cs = db.scalars(select(Conversa).where(Conversa.tenant_id == u.tenant_id)
                    .order_by(Conversa.atualizada_em.desc()).limit(60)).all()
    out = []
    for c in cs:
        cli = db.get(Cliente, c.cliente_id)
        ult = db.scalar(select(Mensagem).where(Mensagem.conversa_id == c.id, Mensagem.papel != "sistema")
                        .order_by(Mensagem.id.desc()))
        out.append({"id": c.id, "nome": cli.nome or cli.telefone, "telefone": cli.telefone,
                    "humano": c.humano, "atualizada_em": c.atualizada_em.isoformat(),
                    "ultima": ult.texto if ult else ""})
    return out


@router.get("/conversas/{conversa_id}")
def mensagens(conversa_id: int, u=Depends(auth.usuario_atual), db=Depends(auth.get_db)):
    c = _conversa(db, u, conversa_id)
    ms = db.scalars(select(Mensagem).where(Mensagem.conversa_id == c.id)
                    .order_by(Mensagem.id.desc()).limit(100)).all()[::-1]
    return {"humano": c.humano,
            "mensagens": [{"id": m.id, "papel": m.papel, "texto": m.texto,
                           "quando": m.created_at.isoformat()} for m in ms]}


@router.post("/conversas/{conversa_id}/humano")
def alternar(conversa_id: int, d: Humano, u=Depends(auth.usuario_atual), db=Depends(auth.get_db)):
    c = _conversa(db, u, conversa_id)
    c.humano = d.humano
    db.add(Mensagem(conversa_id=c.id, papel="sistema",
                    texto="A equipe assumiu a conversa" if d.humano else "A conversa voltou para a IA"))
    db.commit()
    return {"ok": True}


@router.post("/conversas/{conversa_id}/enviar")
def enviar(conversa_id: int, d: Texto, u=Depends(auth.usuario_atual), db=Depends(auth.get_db)):
    c = _conversa(db, u, conversa_id)
    texto = d.texto.strip()
    if not texto:
        raise HTTPException(400, "Escreva uma mensagem")
    t, cli = db.get(Tenant, u.tenant_id), db.get(Cliente, c.cliente_id)
    try:
        whatsapp.enviar_texto(t.instancia, cli.telefone, texto)
    except Exception:
        raise HTTPException(502, "Não foi possível enviar pelo WhatsApp. Verifique a conexão.")
    c.humano = True  # quem responde pelo painel assume a conversa
    c.atualizada_em = agora()
    db.add(Mensagem(conversa_id=c.id, papel="humano", texto=texto))
    db.commit()
    return {"ok": True}
