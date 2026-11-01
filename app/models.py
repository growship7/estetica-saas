from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (Boolean, DateTime, ForeignKey, Index, Integer, Numeric,
                        String, Text, Time, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import agora
from .db import Base

PORTES = ("hatch", "sedan", "suv", "pickup")


class Tenant(Base):
    """Uma empresa cliente. Todo o resto carrega tenant_id."""
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    instancia: Mapped[str | None] = mapped_column(String(80), unique=True)  # instância na Evolution API
    boxes: Mapped[int] = mapped_column(Integer, default=1)  # quantos carros ao mesmo tempo
    instrucoes: Mapped[str] = mapped_column(Text, default="")  # endereço, pagamento, tom de voz...
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=agora)


class Servico(Base):
    __tablename__ = "servicos"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str] = mapped_column(Text, default="")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    precos: Mapped[list["PrecoServico"]] = relationship(
        cascade="all, delete-orphan", order_by="PrecoServico.id")


class PrecoServico(Base):
    """Preço e duração dependem do porte do veículo."""
    __tablename__ = "precos_servico"
    __table_args__ = (UniqueConstraint("servico_id", "porte"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    servico_id: Mapped[int] = mapped_column(ForeignKey("servicos.id"), index=True)
    porte: Mapped[str] = mapped_column(String(10))
    preco: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    duracao_min: Mapped[int] = mapped_column(Integer)


class Horario(Base):
    """Funcionamento por dia da semana (0 = segunda). Sem linha = fechado."""
    __tablename__ = "horarios"
    __table_args__ = (UniqueConstraint("tenant_id", "dia_semana"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    dia_semana: Mapped[int] = mapped_column(Integer)
    abre: Mapped[time] = mapped_column(Time)
    fecha: Mapped[time] = mapped_column(Time)


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (UniqueConstraint("tenant_id", "telefone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    telefone: Mapped[str] = mapped_column(String(40))
    nome: Mapped[str | None] = mapped_column(String(120))


class Veiculo(Base):
    __tablename__ = "veiculos"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    modelo: Mapped[str] = mapped_column(String(80))
    placa: Mapped[str | None] = mapped_column(String(10))
    porte: Mapped[str] = mapped_column(String(10))


class Agendamento(Base):
    __tablename__ = "agendamentos"
    __table_args__ = (Index("ix_agend_tenant_inicio", "tenant_id", "inicio"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    veiculo_id: Mapped[int] = mapped_column(ForeignKey("veiculos.id"))
    servico_id: Mapped[int] = mapped_column(ForeignKey("servicos.id"))
    inicio: Mapped[datetime] = mapped_column(DateTime)
    fim: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(15), default="confirmado")  # confirmado|cancelado|concluido
    origem: Mapped[str] = mapped_column(String(10), default="ia")  # ia|manual
    preco: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=agora)
    servico: Mapped["Servico"] = relationship()
    veiculo: Mapped["Veiculo"] = relationship()


class Conversa(Base):
    __tablename__ = "conversas"
    __table_args__ = (UniqueConstraint("tenant_id", "cliente_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    humano: Mapped[bool] = mapped_column(Boolean, default=False)  # True = IA pausada
    atualizada_em: Mapped[datetime] = mapped_column(DateTime, default=agora)


class Mensagem(Base):
    __tablename__ = "mensagens"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversa_id: Mapped[int] = mapped_column(ForeignKey("conversas.id"), index=True)
    papel: Mapped[str] = mapped_column(String(10))  # cliente|ia|humano|sistema
    texto: Mapped[str] = mapped_column(Text)
    wa_id: Mapped[str | None] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=agora)
