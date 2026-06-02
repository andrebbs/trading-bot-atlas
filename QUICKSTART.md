# 🚀 Guia de Início Rápido

## ✅ Projeto Pronto!

Seu bot de trading foi **reorganizado profissionalmente** e está pronto para uso!

## 📁 O que foi feito

✅ Projeto reorganizado em estrutura profissional
✅ Bot do Telegram criado com alertas automáticos
✅ Documentação completa
✅ Tudo testado e funcionando

## 🎯 Duas Formas de Usar

### 1️⃣ Terminal (Funciona Agora!)

```bash
# Análise do mercado atual
python3 main.py analyze

# Backtesting
python3 main.py backtest

# Paper trading (simulação)
python3 main.py paper
```

### 2️⃣ Bot do Telegram (Alertas Automáticos!)

#### Passo 1: Instalar biblioteca

```bash
pip3 install python-telegram-bot==20.7
```

#### Passo 2: Criar bot no Telegram

1. Abra o Telegram
2. Procure por: **@BotFather**
3. Envie: `/newbot`
4. Escolha nome do bot
5. Copie o **TOKEN**

#### Passo 3: Obter seu Chat ID

1. Procure por: **@userinfobot**
2. Envie: `/start`
3. Copie seu **Chat ID**

#### Passo 4: Criar arquivo .env

```bash
# Na raiz do projeto (/home/abbs/trading-bot)
nano .env
```

Cole isso (substitua pelos seus valores):

```bash
TELEGRAM_BOT_TOKEN=SEU_TOKEN_AQUI
TELEGRAM_CHAT_ID=SEU_CHAT_ID_AQUI
```

Salve: `Ctrl+O` + Enter + `Ctrl+X`

#### Passo 5: Executar o bot

```bash
python3 src/bots/telegram_bot.py
```

Você verá:
```
🤖 Iniciando Bot do Telegram...
📊 Monitorando: SOL/USDT (1m)
✅ Bot iniciado com sucesso!
📱 Procure seu bot no Telegram e envie /start
```

#### Passo 6: Usar no Telegram

Procure seu bot no Telegram e envie:

- `/start` - Ver comandos
- `/analise` - Análise completa
- `/btc` - Análise Bitcoin
- `/sol` - Análise Solana
- `/monitor on` - **Ativar alertas! 🚨**

## 🔔 Alertas Automáticos

Quando você enviar `/monitor on`, o bot vai te enviar mensagens assim:

```
🚨 ALERTA DE SINAL!

🟢 COMPRA - SOL/USDT

💵 Preço: $83.01
📊 Score: 0.756
📈 Probabilidade: 75.6%

💡 Sugestões:
🛡 Stop Loss: $81.34
🎯 Take Profit: $84.69
```

**Você recebe notificações automáticas sem precisar olhar o terminal!**

## 📚 Documentação

- **README.md** - Visão geral do projeto
- **docs/TELEGRAM_BOT.md** - Guia completo do bot Telegram
- **docs/README.md** - Documentação técnica original
- **INSTALL.md** - Instalação detalhada

## ⚙️ Configurações

Edite `config/config.py` para mudar:

```python
SYMBOL = 'SOL/USDT'     # Ativo (BTC/USDT, ETH/USDT, etc)
TIMEFRAME = '1m'        # Período (1m, 5m, 15m, 1h, 4h, 1d)
BUY_THRESHOLD = 0.65    # Score mínimo para COMPRA
SELL_THRESHOLD = 0.35   # Score máximo para VENDA
```

Ou use comandos do Telegram:
- `/ativo BTC/USDT` - Muda ativo
- `/timeframe 5m` - Muda período

## 🆘 Precisa de Ajuda?

### Problema: Bot não responde no Telegram
- ✅ Verificar se o token está correto no `.env`
- ✅ Enviar `/start` para o bot primeiro
- ✅ Ver logs: `cat logs/telegram_bot.log`

### Problema: Não recebo alertas
- ✅ Verificar se o Chat ID está correto
- ✅ Enviar `/monitor on`
- ✅ Aguardar alguns minutos (verifica a cada 5 minutos)

### Problema: Erro ao instalar python-telegram-bot
```bash
pip3 install --upgrade pip
pip3 install python-telegram-bot==20.7
```

## 📊 Estrutura do Projeto

```
trading-bot/
├── main.py                    # ✅ Script principal (funciona!)
├── src/
│   ├── core/                  # ✅ Módulos de análise
│   └── bots/
│       └── telegram_bot.py    # 🆕 Bot do Telegram
├── config/
│   └── config.py              # ⚙️ Configurações
├── docs/                      # 📚 Documentação
├── logs/                      # 📝 Logs
└── reports/                   # 📊 Relatórios
```

## 🎓 Exemplo de Uso

### Análise Rápida
```bash
$ python3 main.py analyze

🟢 RECOMENDAÇÃO: COMPRA
💵 Preço: $82.98
📊 Score: 1.080
```

### Bot no Telegram
```
Você: /btc
Bot: 🟢 COMPRA - BTC/USDT
     💵 $67,243.90
     📊 Score: 0.782

Você: /monitor on  
Bot: ✅ Monitoramento ATIVADO!
     Você receberá alertas automáticos
```

## 🎯 Próximos Passos Recomendados

1. **Teste no terminal:**
   ```bash
   python3 main.py analyze
   ```

2. **Instale biblioteca do Telegram:**
   ```bash
   pip3 install python-telegram-bot==20.7
   ```

3. **Configure o bot:** Siga passos 2-4 acima

4. **Execute:**
   ```bash
   python3 src/bots/telegram_bot.py
   ```

5. **Ative alertas:** `/monitor on` no Telegram

## 💡 Dicas

- ✅ Use **terminal** para testes e análises pontuais
- ✅ Use **Telegram bot** para monitoramento contínuo
- ✅ Mantenha o bot rodando em VPS para alertas 24/7
- ✅ Configure stop loss e take profit conforme sugerido
- ✅ Teste com paper trading antes de usar dinheiro real

---

**Agora você tem um sistema profissional de análise técnica com alertas automáticos! 🚀**

Qualquer dúvida, consulte as documentações na pasta `docs/`
