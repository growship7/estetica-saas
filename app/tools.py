"""Ferramentas que o Claude pode chamar.

A IA nunca inventa preço nem horário: tudo passa por aqui, e o backend valida.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, text

from .availability import horarios_livres
from .config import agora
from .models import (PORTES, Agendamento, Cliente, Conversa, Mensagem,
                     PrecoServico, Servico, Tenant, Veiculo)

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
FMT = "%Y-%m-%d %H:%M"


@dataclass
class Ctx:
    db: object
    tenant: Tenant
    cliente: Cliente
    conversa: Conversa


_PORTE = {"type": "string", "enum": list(PORTES), "description": "Porte do veículo"}

TOOLS = [
    {"name": "listar_servicos",
     "description": "Lista os serviços da empresa com preço e duração. Passe o porte para ver só os valores dele.",
     "input_schema": {"type": "object", "properties": {"porte": _PORTE}}},
    {"name": "checar_disponibilidade",
     "description": "Devolve os horários livres de um dia para um serviço. Lista vazia = fechado ou lotado.",
     "input_schema": {"type": "object", "required": ["servico_id", "porte", "data"],
                      "properties": {"servico_id": {"type": "integer"}, "porte": _PORTE,
                                     "data": {"type": "string", "description": "AAAA-MM-DD"}}}},
    {"name": "criar_agendamento",
     "description": "Cria o agendamento. Só use depois de o cliente confirmar serviço, carro, horário e nome.",
     "input_schema": {"type": "object",
                      "required": ["servico_id", "porte", "inicio", "nome_cliente", "modelo_veiculo"],
                      "properties": {"servico_id": {"type": "integer"}, "porte": _PORTE,
                                     "inicio": {"type": "string", "description": "AAAA-MM-DD HH:MM"},
                                     "nome_cliente": {"type": "string"},
                                     "modelo_veiculo": {"type": "string"},
                                     "placa": {"type": "string"}}}},
    {"name": "listar_meus_agendamentos",
     "description": "Lista os agendamentos futuros deste cliente.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "cancelar_agendamento",
     "description": "Cancela um agendamento deste cliente.",
     "input_schema": {"type": "object", "required": ["agendamento_id"],
                      "properties": {"agendamento_id": {"type": "integer"}}}},
    {"name": "remarcar_agendamento",
     "description": "Muda o horário de um agendamento deste cliente para um horário livre.",
     "input_schema": {"type": "object", "required": ["agendamento_id", "novo_inicio"],
                      "properties": {"agendamento_id": {"type": "integer"},
                                     "novo_inicio": {"type": "string", "description": "AAAA-MM-DD HH:MM"}}}},
    {"name": "chamar_humano",
     "description": "Passa a conversa para uma pessoa da equipe. Use em reclamações, pedidos fora do padrão ou quando o cliente pedir para falar com alguém.",
     "input_schema": {"type": "object", "properties": {"motivo": {"type": "string"}}}},
]


def _servico_preco(ctx, servico_id, porte):
    s = ctx.db.scalar(select(Servico).where(
        Servico.id == servico_id, Servico.tenant_id == ctx.tenant.id, Servico.ativo.is_(True)))
    p = ctx.db.scalar(select(PrecoServico).where(
        PrecoServico.servico_id == servico_id, PrecoServico.porte == porte)) if s else None
    if not s or not p:
        raise ValueError("serviço ou porte inválido")
    return s, p


def _dt(valor: str) -> datetime:
    return datetime.strptime(valor.strip().replace("T", " "), FMT)


def _travar(ctx):
    """Evita dois agendamentos no mesmo horário quando duas conversas chegam juntas."""
    if ctx.db.get_bind().dialect.name == "postgresql":
        ctx.db.execute(text("select pg_advisory_xact_lock(:k)"), {"k": ctx.tenant.id})


def _meu_agendamento(ctx, agendamento_id) -> Agendamento:
    a = ctx.db.scalar(select(Agendamento).where(
        Agendamento.id == agendamento_id, Agendamento.tenant_id == ctx.tenant.id,
        Agendamento.cliente_id == ctx.cliente.id, Agendamento.status == "confirmado"))
    if not a:
        raise ValueError("agendamento não encontrado")
    return a


def listar_servicos(ctx, porte=None):
    servicos = ctx.db.scalars(select(Servico).where(
        Servico.tenant_id == ctx.tenant.id, Servico.ativo.is_(True)).order_by(Servico.id)).all()
    saida = []
    for s in servicos:
        precos = {p.porte: {"preco": float(p.preco), "duracao_min": p.duracao_min} for p in s.precos}
        if porte:
            precos = {porte: precos[porte]} if porte in precos else {}
        saida.append({"id": s.id, "nome": s.nome, "descricao": s.descricao, "precos": precos})
    return {"servicos": saida}


def checar_disponibilidade(ctx, servico_id, porte, data):
    _, p = _servico_preco(ctx, servico_id, porte)
    dia = datetime.strptime(data.strip(), "%Y-%m-%d").date()
    if dia < agora().date():
        return {"erro": "essa data já passou"}
    livres = horarios_livres(ctx.db, ctx.tenant, dia, p.duracao_min)
    return {"data": data, "dia_semana": DIAS[dia.weekday()], "duracao_min": p.duracao_min,
            "horarios_livres": [h.strftime("%H:%M") for h in livres]}


def criar_agendamento(ctx, servico_id, porte, inicio, nome_cliente, modelo_veiculo, placa=None):
    s, p = _servico_preco(ctx, servico_id, porte)
    ini = _dt(inicio)
    _travar(ctx)
    livres = horarios_livres(ctx.db, ctx.tenant, ini.date(), p.duracao_min)
    if ini not in livres:
        ctx.db.rollback()
        return {"erro": "esse horário não está disponível",
                "outros_horarios_no_dia": [h.strftime("%H:%M") for h in livres][:8]}
    if nome_cliente.strip():
        ctx.cliente.nome = nome_cliente.strip()
    placa = placa.strip().upper() if placa else None
    q = select(Veiculo).where(Veiculo.tenant_id == ctx.tenant.id, Veiculo.cliente_id == ctx.cliente.id)
    q = q.where(Veiculo.placa == placa) if placa else q.where(
        func.lower(Veiculo.modelo) == modelo_veiculo.strip().lower())
    veic = ctx.db.scalar(q) or Veiculo(tenant_id=ctx.tenant.id, cliente_id=ctx.cliente.id,
                                       modelo=modelo_veiculo.strip(), placa=placa, porte=porte)
    ctx.db.add(veic)
    ctx.db.flush()
    ag = Agendamento(tenant_id=ctx.tenant.id, cliente_id=ctx.cliente.id, veiculo_id=veic.id,
                     servico_id=s.id, inicio=ini, fim=ini + timedelta(minutes=p.duracao_min),
                     preco=p.preco, origem="ia")
    ctx.db.add(ag)
    ctx.db.commit()
    return {"ok": True, "agendamento_id": ag.id, "servico": s.nome, "veiculo": veic.modelo,
            "inicio": ag.inicio.strftime(FMT), "termino_previsto": ag.fim.strftime(FMT),
            "preco": float(p.preco)}


def listar_meus_agendamentos(ctx):
    ags = ctx.db.scalars(select(Agendamento).where(
        Agendamento.tenant_id == ctx.tenant.id, Agendamento.cliente_id == ctx.cliente.id,
        Agendamento.status == "confirmado", Agendamento.inicio >= agora())
        .order_by(Agendamento.inicio)).all()
    return {"agendamentos": [{"id": a.id, "servico": a.servico.nome, "veiculo": a.veiculo.modelo,
                              "inicio": a.inicio.strftime(FMT)} for a in ags]}


def cancelar_agendamento(ctx, agendamento_id):
    a = _meu_agendamento(ctx, agendamento_id)
    a.status = "cancelado"
    ctx.db.commit()
    return {"ok": True}


def remarcar_agendamento(ctx, agendamento_id, novo_inicio):
    a = _meu_agendamento(ctx, agendamento_id)
    novo = _dt(novo_inicio)
    dur = int((a.fim - a.inicio).total_seconds() // 60)
    _travar(ctx)
    livres = horarios_livres(ctx.db, ctx.tenant, novo.date(), dur, ignorar_id=a.id)
    if novo not in livres:
        ctx.db.rollback()
        return {"erro": "esse horário não está disponível",
                "outros_horarios_no_dia": [h.strftime("%H:%M") for h in livres][:8]}
    a.inicio, a.fim = novo, novo + timedelta(minutes=dur)
    ctx.db.commit()
    return {"ok": True, "agendamento_id": a.id, "inicio": a.inicio.strftime(FMT)}


def chamar_humano(ctx, motivo=""):
    ctx.conversa.humano = True
    ctx.db.add(Mensagem(conversa_id=ctx.conversa.id, papel="sistema",
                        texto=f"IA passou a conversa para a equipe. Motivo: {motivo or 'não informado'}"))
    ctx.db.commit()
    return {"ok": True}


FUNCOES = {f.__name__: f for f in (
    listar_servicos, checar_disponibilidade, criar_agendamento, listar_meus_agendamentos,
    cancelar_agendamento, remarcar_agendamento, chamar_humano)}


def executar(ctx: Ctx, nome: str, args: dict) -> dict:
    try:
        return FUNCOES[nome](ctx, **(args or {}))
    except (ValueError, TypeError, KeyError) as e:
        ctx.db.rollback()
        return {"erro": f"dados inválidos: {e}"}
