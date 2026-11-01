# Estética SaaS: backend (núcleo)

IA (Claude) que atende no WhatsApp e agenda serviços de estética automotiva. Multi-tenant.

## Rodar local
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...
    python -m tests.test_core                        # teste sem API/WhatsApp
    python -m app.seed "Brilho Auto" brilho brilho-inst 2
    uvicorn app.main:app --reload

## Ligar no WhatsApp (Evolution API v2)
Na instância do cliente, webhook → `https://SEU-DOMINIO/webhook/evolution?token=WEBHOOK_SECRET`, evento `MESSAGES_UPSERT`.
O nome da instância precisa ser igual ao campo `instancia` da empresa.

## Estrutura
- `app/models.py`: banco (tudo com `tenant_id`)
- `app/availability.py`: horários livres (expediente + boxes)
- `app/tools.py`: ferramentas que o Claude chama (a IA nunca inventa horário/preço)
- `app/agent.py`: prompt + loop do Claude
- `app/whatsapp.py`: envio e leitura do webhook da Evolution
- `app/main.py`: webhook e processamento
- `app/seed.py`: cria empresa com serviços padrão e horários
