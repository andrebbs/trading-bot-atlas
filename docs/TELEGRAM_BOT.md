# Guia de Instalação e Uso do Bot do Telegram

## 📱 Como criar seu Bot no Telegram

### Passo 1: Criar o Bot com BotFather

1. Abra o Telegram e procure por **@BotFather**
2. Envie o comando `/newbot`
3. Escolha um nome para seu bot (ex: "Meu Bot de Trading")
4. Escolha um username (deve terminar com 'bot', ex: "MeuTradingBot")
5. O BotFather vai te dar um **TOKEN** - copie e guarde!

### Passo 2: Obter seu Chat ID

1. Procure por **@userinfobot** no Telegram
2. Envie `/start`
3. O bot vai mostrar seu **Chat ID** - copie este número!

## ⚙️ Configuração

### Opção 1: Arquivo .env (Recomendado)

Crie um arquivo `.env` na raiz do projeto:

```bash
# Token do bot (obtido com @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Seu Chat ID (obtido com @userinfobot)
TELEGRAM_CHAT_ID=123456789
```

### Opção 2: Editar config.py

Abra `config/config.py` e adicione:

```python
# Telegram
TELEGRAM_BOT_TOKEN = '123456789:ABCdefGHIjklMNOpqrsTUVwxyz'
TELEGRAM_CHAT_ID = '123456789'  # Seu chat ID para receber alertas
```

## 📦 Instalação da Biblioteca

```bash
pip3 install python-telegram-bot==20.7
```

## 🚀 Executar o Bot

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

## 💬 Comandos Disponíveis

### Análise de Mercado
- `/analise` - Análise completa do ativo atual configurado
- `/btc` - Análise do Bitcoin (BTC/USDT)
- `/eth` - Análise do Ethereum (ETH/USDT)
- `/sol` - Análise do Solana (SOL/USDT)
- `/bnb` - Análise do BNB (BNB/USDT)

### Configuração
- `/config` - Ver configuração atual
- `/timeframe 1m` - Mudar timeframe (1m, 5m, 15m, 1h, 4h, 1d)
- `/ativo BTC/USDT` - Mudar ativo analisado

### Monitoramento Automático
- `/monitor on` - Ativa alertas automáticos
- `/monitor off` - Desativa alertas

Quando ativado, você receberá **alertas automáticos** sempre que um sinal de COMPRA ou VENDA aparecer!

### Outros
- `/help` - Mostra todos os comandos
- `/ping` - Testa se o bot está online

## 📊 Exemplos de Uso

### Análise Rápida
```
Você: /btc

Bot: 🟢 ANÁLISE DE BTC/USDT
📅 12/01/2025 15:30:45
💵 Preço Atual: $67,243.90
🎯 RECOMENDAÇÃO: COMPRA
📊 Score: 0.782
📈 Probabilidade: 78.2%
...
```

### Configurar Monitoramento
```
Você: /ativo SOL/USDT
Bot: ✅ Ativo alterado para: SOL/USDT

Você: /timeframe 5m
Bot: ✅ Timeframe alterado para: 5m

Você: /monitor on
Bot: ✅ Monitoramento ATIVADO!
📊 Monitorando: SOL/USDT (5m)
```

Agora você receberá notificações automáticas!

## 🔔 Alertas Automáticos

Quando o monitoramento está ativo, você recebe mensagens assim:

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

## 🔧 Solução de Problemas

### Bot não responde
1. Verifique se o token está correto
2. Certifique-se de que enviou `/start` para o bot
3. Verifique os logs em `logs/telegram_bot.log`

### Não recebe alertas
1. Verifique se adicionou o `TELEGRAM_CHAT_ID` corretamente
2. Ative o monitoramento com `/monitor on`
3. Aguarde alguns minutos (verifica a cada 5 minutos)

### Erro ao instalar python-telegram-bot
```bash
# Se tiver problema, use:
pip3 install --upgrade pip
pip3 install python-telegram-bot==20.7
```

## 🎯 Dicas

1. **Use /monitor on** para receber alertas automáticos
2. **Configure o timeframe** de acordo com seu estilo de trade
3. **Analise vários ativos** com /btc, /eth, /sol, /bnb
4. **Mantenha o bot rodando** em um servidor ou VPS para alertas 24/7

## 🔐 Segurança

⚠️ **IMPORTANTE:**
- Nunca compartilhe seu `TELEGRAM_BOT_TOKEN`
- Não commite o arquivo `.env` no Git
- O `.gitignore` já está configurado para proteger suas credenciais

## 📁 Estrutura de Arquivos

```
trading-bot/
├── src/
│   └── bots/
│       └── telegram_bot.py  ← Bot do Telegram
├── config/
│   └── config.py            ← Configurações
├── .env                      ← Tokens (criar)
├── .env.example              ← Exemplo
└── logs/
    └── telegram_bot.log      ← Logs do bot
```

## 🚀 Executar em Produção

Para manter o bot rodando 24/7:

```bash
# Usando nohup
nohup python3 src/bots/telegram_bot.py > logs/bot.log 2>&1 &

# Ou usando screen
screen -S telegram_bot
python3 src/bots/telegram_bot.py
# Pressione Ctrl+A, depois D para desanexar
```

## 📞 Suporte

Se encontrar problemas:
1. Verifique os logs: `cat logs/telegram_bot.log`
2. Teste a análise manual: `python3 main.py analyze`
3. Verifique a conexão: `/ping` no bot
