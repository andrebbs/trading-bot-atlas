# Configuração MT5 para Linux

Este guia mostra como configurar o MetaTrader 5 no Linux para usar sinais ao vivo com o bot de trading.

## 📋 Pré-requisitos

- Linux (Ubuntu/Debian)
- Wine instalado ✅ (já detectado no sistema)
- Conta na corretora Fundscap
- Terminal MT5 da Fundscap

## 🔧 Instalação do MT5 no Linux

### Método 1: Via Wine (Recomendado)

```bash
# 1. Baixar terminal MT5 da Fundscap
wget https://download.mql5.com/cdn/web/fundscap.limited/mt5/fundscap5setup.exe

# 2. Instalar via Wine
wine fundscap5setup.exe

# 3. Após instalação, executar MT5
wine ~/.wine/drive_c/Program\ Files/Fundscap\ MetaTrader\ 5/terminal64.exe
```

### Método 2: Via PlayOnLinux (Alternativa)

```bash
# Instalar PlayOnLinux
sudo apt install playonlinux

# Abrir PlayOnLinux e instalar MT5 via assistente
playonlinux
```

## 📦 Instalação da Biblioteca Python

**IMPORTANTE**: A biblioteca `MetaTrader5` oficial só funciona no Windows.

Para Linux, temos 2 opções:

### Opção A: Usar MT5 via Wine + Biblioteca Windows

Requer configuração avançada com Python no Wine. **Não recomendado**.

### Opção B: Usar API REST/WebSocket (Se disponível)

Verificar se Fundscap oferece API REST ou WebSocket para acesso.

### Opção C: Usar ponte TCP local (Recomendado)

Criar script que roda no Windows/Wine e expõe dados via socket local.

## 🚀 Configuração para o Bot

Após instalar MT5:

1. **Abrir MT5 e fazer login** na conta Fundscap
2. **Configurar Expert Advisor** para exportar dados
3. **Ativar AutoTrading** no MT5
4. **Configurar .env** no bot:

```bash
# Adicionar ao .env
MT5_ENABLED=true
MT5_SERVER=Fundscap-Demo  # ou Fundscap-Real
MT5_LOGIN=seu_login
MT5_PASSWORD=sua_senha
```

## ✅ Teste de Conexão

```bash
# No terminal do projeto
python3 -c "
from src.core.mt5_connector import MT5Connector
mt5 = MT5Connector()
if mt5.connect():
    print('✅ MT5 conectado!')
    print(f'Conta: {mt5.account_info()}')
else:
    print('❌ Falha na conexão MT5')
"
```

## 📊 Ativos Suportados

Configurados na sua conta Fundscap:
- **CAD/JPY** - Forex
- **XAUUSD** - Gold
- **HK50** - Hong Kong Index 50

## 🔗 Links Úteis

- [MetaTrader 5 Wine HQ](https://appdb.winehq.org/objectManager.php?sClass=application&iId=14333)
- [Documentação MT5 Python](https://www.mql5.com/en/docs/python_metatrader5)
- [Fundscap](https://www.fundscap.com)

## ⚠️ Status Atual

**Em desenvolvimento**: A integração MT5 está sendo implementada.

Por enquanto, use:
- `/otcbacktest` - para validar estratégias no histórico PocketOption
- Operação manual no MT5 seguindo sinais validados

## 🆘 Troubleshooting

### MT5 não abre no Wine
```bash
# Instalar dependências Wine
winetricks vcrun2015 dotnet48
```

### Erro de conexão com servidor
- Verificar firewall
- Testar login manual no MT5
- Verificar nome correto do servidor (Fundscap-Demo ou Fundscap-Real)

### Python não encontra MT5
- No Linux, implementar via socket/API REST
- Alternativa: rodar bot no Windows com MT5 nativo
