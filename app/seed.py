"""Cria uma empresa já pronta para uso.  python -m app.seed "Brilho Auto" brilho brilho-inst [boxes]"""
import sys
from datetime import time

from .db import Base, SessionLocal, engine
from .models import PORTES, Horario, PrecoServico, Servico, Tenant

# (nome, descrição, duração em min, preços na ordem de PORTES: hatch, sedan, suv, pickup)
# Valores são só um ponto de partida: o dono ajusta no painel.
PADRAO = [
    ("Lavagem simples", "Lavagem externa e aspiração.", 45, (40, 50, 60, 70)),
    ("Lavagem completa", "Lavagem detalhada por fora e por dentro, pneus e painel.", 90, (80, 100, 120, 140)),
    ("Higienização interna", "Limpeza profunda de bancos, carpetes e forros.", 180, (250, 300, 350, 400)),
    ("Polimento comercial", "Remove riscos leves e devolve o brilho da pintura.", 240, (350, 420, 500, 580)),
    ("Vitrificação de pintura", "Proteção cerâmica da pintura, brilho de longa duração.", 480, (900, 1100, 1300, 1500)),
]


def criar_tenant(db, nome: str, slug: str, instancia: str, boxes: int = 1, instrucoes: str = "") -> Tenant:
    t = Tenant(nome=nome, slug=slug, instancia=instancia, boxes=boxes, instrucoes=instrucoes)
    db.add(t)
    db.flush()
    for nome_s, desc, dur, precos in PADRAO:
        s = Servico(tenant_id=t.id, nome=nome_s, descricao=desc)
        s.precos = [PrecoServico(porte=porte, preco=preco, duracao_min=dur)
                    for porte, preco in zip(PORTES, precos)]
        db.add(s)
    for dia in range(5):  # segunda a sexta
        db.add(Horario(tenant_id=t.id, dia_semana=dia, abre=time(8), fecha=time(18)))
    db.add(Horario(tenant_id=t.id, dia_semana=5, abre=time(8), fecha=time(13)))  # sábado
    db.commit()
    return t


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        t = criar_tenant(db, sys.argv[1], sys.argv[2], sys.argv[3],
                         boxes=int(sys.argv[4]) if len(sys.argv) > 4 else 1)
        print(f"Empresa criada: id={t.id} instancia={t.instancia}")
