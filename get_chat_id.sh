#!/bin/bash
# Script para obter TELEGRAM_CHAT_ID automaticamente

echo "🔍 Buscando Chat IDs..."

# Le o token do .env (nunca hardcode o token aqui)
BOT_TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" .env | head -1 | cut -d'=' -f2-)
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ TELEGRAM_BOT_TOKEN não encontrado em .env. Defina-o antes de rodar este script."
    exit 1
fi

RESPONSE=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates")

CHAT_ID=$(echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for msg in data.get('result', []):
    if 'message' in msg and 'chat' in msg['message']:
        print(msg['message']['chat']['id'])
        break
else:
    print('')
")

if [ -z "$CHAT_ID" ]; then
    echo "❌ Nenhum Chat ID encontrado."
    echo ""
    echo "📱 Faça isso primeiro:"
    echo "1. Abra o Telegram"
    echo "2. Procure o bot configurado em TELEGRAM_BOT_TOKEN"
    echo "3. Envie /start"
    echo "4. Rode este script novamente"
    echo ""
    echo "OU use @userinfobot no Telegram e copie seu Id"
else
    echo "✅ Chat ID encontrado: $CHAT_ID"
    echo ""
    echo "Atualizando .env..."
    
    if grep -q "^TELEGRAM_CHAT_ID=" .env; then
        sed -i "s/^TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=$CHAT_ID/" .env
        echo "✅ .env atualizado com sucesso!"
    else
        echo "TELEGRAM_CHAT_ID=$CHAT_ID" >> .env
        echo "✅ TELEGRAM_CHAT_ID adicionado ao .env!"
    fi
    
    echo ""
    echo "🤖 Reinicie o bot agora:"
    echo "   pkill -f telegram_bot.py"
    echo "   python3 src/bots/telegram_bot.py"
fi
