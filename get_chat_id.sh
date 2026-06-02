#!/bin/bash
# Script para obter TELEGRAM_CHAT_ID automaticamente

echo "🔍 Buscando Chat IDs..."
RESPONSE=$(curl -s "https://api.telegram.org/bot8686156909:AAFPYCDrcPR0icN_JaB3WCa5fPF-hTB1AgE/getUpdates")

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
    echo "2. Procure @Abbscryptobot"
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
