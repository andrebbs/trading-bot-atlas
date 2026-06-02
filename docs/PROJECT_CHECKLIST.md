# Project Checklist (Next Steps)

## 1. Monitoramento Telegram (feito)
- [x] Ciclo a cada 5 minutos
- [x] Rotacao de 1 ativo por ciclo
- [x] Encerramento automatico apos 4 sinais
- [x] Requer novo /monitor on para reiniciar

## 2. Martingale controlado (pendente)
- [ ] Implementar parametro em config: MARTINGALE_STEPS = 0|1|2
- [ ] Trava de risco diario (loss cap)
- [ ] Bloquear Martingale em volatilidade extrema (ATR gate)
- [ ] Backtest comparativo oficial 0x vs 1x vs 2x
- [ ] Expor resultados no report JSON

## 3. Base de estrategias OTC/PocketOption (feito: v1)
- [x] Catalogo estruturado em JSON
- [x] Modulo de consulta e compatibilidade tecnica
- [x] CLI: python3 main.py strategy

## 4. Base OTC (proxima iteracao)
- [ ] Criar scoring de qualidade por estrategia (winrate em paper)
- [ ] Normalizar regras de entrada/saida para simulador unico
- [ ] Versao com janela horaria (sessao EU/US)
- [ ] Historico de performance por ativo e timeframe

## 5. Arquitetura futura (agente / knowledge base / MCP)
- [ ] Definir formato unico de conhecimento (JSON/YAML)
- [ ] Adicionar pipeline de ingestao de novos textos de canal
- [ ] API interna para recomendacao de setup por contexto
- [ ] Opcional: MCP server para consulta externa

## Comandos uteis
- `python3 main.py strategy`
- `python3 main.py strategy --timeframe 15m --max-risk low`
- `python3 main.py backtest`
