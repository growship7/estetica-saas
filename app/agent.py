import json

import anthropic
from sqlalchemy import select

from . import config
from .models import Mensagem
from .tools import DIAS, TOOLS, Ctx, executar

_client = None
MAX_VOLTAS = 6  # limite de chamadas de ferramenta por mensagem


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente
    return _client


def _sistema(tenant) -> list[dict]:
    fixo = f"""Você é a atendente virtual da {tenant.nome}, uma estética automotiva. Atende clientes pelo WhatsApp.

Estilo: português do Brasil, natural e simpático, como uma atendente de verdade no WhatsApp. Mensagens curtas (1 a 3 frases), sem markdown e sem listas longas, no máximo um emoji de vez em quando. Faça uma pergunta por vez. Se perguntarem se você é um robô ou IA, diga a verdade: é a assistente virtual da empresa.

Regras:
- Nunca invente serviço, preço, horário ou política. Consulte as ferramentas.
- Preço e duração dependem do porte do veículo (hatch, sedan, suv, pickup). Pergunte o modelo do carro e deduza o porte; se tiver dúvida, pergunte.
- Para agendar você precisa de: serviço, modelo do carro, dia, horário (entre os livres) e nome do cliente. Placa é opcional. Confirme os dados com o cliente antes de criar.
- Só diga que agendou depois que criar_agendamento retornar ok. Ao confirmar, repita serviço, dia, horário e valor.
- Reclamação, pedido fora do padrão ou pedido para falar com uma pessoa: use chamar_humano e avise que alguém da equipe responde em breve.
- Não converse sobre assuntos fora da estética automotiva.
- Nunca mencione ferramentas, tabela, consulta ou sistema. Passe só a informação, como quem já sabe (ex.: "O polimento no Onix sai R$ 350 e leva cerca de 4h").
- Não peça desculpa nem comente suas respostas anteriores, a menos que o cliente aponte um erro de verdade.
- Ao confirmar, mostre primeiro o resumo (serviço, carro, dia, horário e valor) e termine com a pergunta "Pode confirmar?".

Informações da empresa:
{tenant.instrucoes or 'Nenhuma informação extra cadastrada.'}"""
    agora = config.agora()
    return [
        {"type": "text", "text": fixo, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"Agora: {DIAS[agora.weekday()]}, {agora.strftime('%Y-%m-%d %H:%M')}."},
    ]


def _historico(db, conversa_id: int) -> list[dict]:
    rows = db.scalars(select(Mensagem).where(
        Mensagem.conversa_id == conversa_id, Mensagem.papel != "sistema")
        .order_by(Mensagem.id.desc()).limit(30)).all()[::-1]
    out: list[dict] = []
    for m in rows:
        role = "user" if m.papel == "cliente" else "assistant"
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n" + m.texto
        else:
            out.append({"role": role, "content": m.texto})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def responder(db, tenant, conversa, cliente) -> str:
    """Gera a resposta para a última mensagem do cliente (já salva em `mensagens`)."""
    msgs = _historico(db, conversa.id)
    ctx = Ctx(db, tenant, cliente, conversa)
    for _ in range(MAX_VOLTAS):
        r = client().messages.create(model=config.ANTHROPIC_MODEL, max_tokens=800,
                                     system=_sistema(tenant), tools=TOOLS, messages=msgs)
        if r.stop_reason != "tool_use":
            texto = "".join(b.text for b in r.content if b.type == "text").strip()
            return texto or "Pode me falar de novo? Não consegui entender direito."
        msgs.append({"role": "assistant", "content": r.content})
        resultados = []
        for b in r.content:
            if b.type == "tool_use":
                saida = executar(ctx, b.name, b.input)
                resultados.append({"type": "tool_result", "tool_use_id": b.id,
                                   "content": json.dumps(saida, ensure_ascii=False, default=str)})
        msgs.append({"role": "user", "content": resultados})
    executar(ctx, "chamar_humano", {"motivo": "IA não conseguiu concluir o atendimento"})
    return "Vou pedir pra alguém da equipe continuar com você por aqui, tá? Já já te respondem."
