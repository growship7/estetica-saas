import os
from datetime import datetime
from zoneinfo import ZoneInfo

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
EVOLUTION_URL = os.getenv("EVOLUTION_URL", "http://growship_evolution-api:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "troque-isso")
FUSO = os.getenv("FUSO", "America/Sao_Paulo")


def agora() -> datetime:
    """Agora no fuso da empresa, sem tzinfo. Todos os horários do banco são locais."""
    return datetime.now(ZoneInfo(FUSO)).replace(tzinfo=None)
