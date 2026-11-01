from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from .config import agora
from .models import Agendamento, Horario, Tenant

PASSO_MIN = 30  # de quanto em quanto tempo oferecemos início de serviço


def _ocupacao(db, tenant_id: int, ini: datetime, fim: datetime, ignorar_id: int | None = None) -> int:
    q = select(func.count()).select_from(Agendamento).where(
        Agendamento.tenant_id == tenant_id,
        Agendamento.status == "confirmado",
        Agendamento.inicio < fim,
        Agendamento.fim > ini,
    )
    if ignorar_id:
        q = q.where(Agendamento.id != ignorar_id)
    return db.scalar(q)


def horarios_livres(db, tenant: Tenant, dia: date, duracao_min: int,
                    ignorar_id: int | None = None) -> list[datetime]:
    """Inícios possíveis no dia: dentro do expediente, no futuro e com box livre."""
    h = db.scalar(select(Horario).where(Horario.tenant_id == tenant.id,
                                        Horario.dia_semana == dia.weekday()))
    if not h:
        return []
    cur = datetime.combine(dia, h.abre)
    limite = datetime.combine(dia, h.fecha)
    dur = timedelta(minutes=duracao_min)
    agora_ = agora()
    livres = []
    while cur + dur <= limite:
        if cur > agora_ and _ocupacao(db, tenant.id, cur, cur + dur, ignorar_id) < tenant.boxes:
            livres.append(cur)
        cur += timedelta(minutes=PASSO_MIN)
    return livres
