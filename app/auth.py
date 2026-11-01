"""Login do painel: senha com scrypt e cookie assinado (só biblioteca padrão).
Criar usuário:  python -m app.auth slug-da-empresa email senha"""
import hashlib, hmac, os, sys, time

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select

from . import config
from .db import Base, SessionLocal, engine
from .models import Tenant, Usuario

SEGREDO = (os.getenv("PANEL_SECRET") or config.WEBHOOK_SECRET).encode()
DURACAO = 14 * 24 * 3600


def hash_senha(senha: str) -> str:
    salt = os.urandom(16)
    return salt.hex() + ":" + hashlib.scrypt(senha.encode(), salt=salt, n=2**14, r=8, p=1).hex()


def confere(senha: str, guardado: str) -> bool:
    salt, h = guardado.split(":")
    novo = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()
    return hmac.compare_digest(novo, h)


def _assina(corpo: str) -> str:
    return hmac.new(SEGREDO, corpo.encode(), hashlib.sha256).hexdigest()


def criar_token(uid: int) -> str:
    corpo = f"{uid}.{int(time.time()) + DURACAO}"
    return f"{corpo}.{_assina(corpo)}"


def ler_token(tok: str | None) -> int | None:
    try:
        uid, exp, sig = tok.split(".")
        if hmac.compare_digest(sig, _assina(f"{uid}.{exp}")) and int(exp) > time.time():
            return int(uid)
    except Exception:
        pass
    return None


def get_db():
    with SessionLocal() as db:
        yield db


def usuario_atual(sessao: str | None = Cookie(None), db=Depends(get_db)) -> Usuario:
    uid = ler_token(sessao)
    u = db.get(Usuario, uid) if uid else None
    if not u:
        raise HTTPException(401, "Faça login para continuar")
    return u


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    slug, email, senha = sys.argv[1:4]
    with SessionLocal() as db:
        t = db.scalar(select(Tenant).where(Tenant.slug == slug))
        if not t:
            sys.exit(f"Empresa '{slug}' não encontrada")
        db.add(Usuario(tenant_id=t.id, email=email.strip().lower(), senha_hash=hash_senha(senha)))
        db.commit()
        print(f"Usuário criado para {t.nome}: {email}")
