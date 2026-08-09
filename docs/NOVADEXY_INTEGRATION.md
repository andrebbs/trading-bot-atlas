# NovaDexy demo — integração skeleton

**Status:** desligada por padrão, com `dry_run` como modo padrão. O executor não implementa conta real: valores fora de `dry_run` e `demo` são recusados.

## Configuração local

No `.env` local (não faça commit do token):

```dotenv
NOVADEXY_EXECUTOR_ENABLED=false
NOVADEXY_ENABLED=false
NOVADEXY_MODE=dry_run
NOVADEXY_BASE_URL=https://novadexybroker.com
NOVADEXY_TOKEN=
NOVADEXY_ACCOUNT_ID=
NOVADEXY_DEFAULT_AMOUNT_CENTS=500
NOVADEXY_DEFAULT_EXPIRATION=1
```

O payload observado usa `amount` em centavos (`500` = R$ 5,00), `direction=1` para compra/up e `direction=0` para venda/down.

## Validar sem enviar ordem

```bash
python scripts/novadexy_demo_smoke.py --symbol BTC/USDT --direction BUY --price 65000
```

Isso apenas exibe o payload. Para uma ordem na **demo**, informe token novo e conta demo localmente, depois:

```bash
NOVADEXY_ENABLED=true NOVADEXY_MODE=demo \
python scripts/novadexy_demo_smoke.py --execute --symbol BTC/USDT --direction BUY --price 65000
```

## ATLAS

O hook no `telegram_bot.py` só roda após o sinal já aprovado e só se `NOVADEXY_EXECUTOR_ENABLED=true`. Mesmo assim, ele segue em dry-run até o modo demo ser configurado. O retorno pode trazer `transaction_id`; ainda é necessário validar manualmente expiração, sessão/cookies e apuração WIN/LOSS.
