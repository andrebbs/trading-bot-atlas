# 🏗️ Refatoração Arquitetural - Fase 1 (Quick Wins)

**Objetivo:** Reduzir `telegram_bot.py` de 5.312 linhas → ~1.500 linhas  
**Tempo Estimado:** 1-2 dias  
**Risco:** Baixo (movimentação de código, sem quebrar funcionalidade)  
**Data Início:** 01/06/2026

---

## 📋 Checklist de Execução

### ✅ Preparação
- [x] Análise de código atual (5.312 linhas em telegram_bot.py)
- [x] Definição de estrutura alvo
- [x] Criação deste documento de acompanhamento
- [ ] Backup do código atual (branch feature/refactor-phase1)

### 🔧 Etapa 1: Criar Estrutura de Diretórios
- [ ] `src/domain/utils/` - Utilitários puros
- [ ] `src/domain/services/` - Serviços de domínio
- [ ] `src/presentation/telegram/handlers/` - Command handlers
- [ ] `src/presentation/telegram/formatters/` - Formatadores de mensagem
- [ ] Adicionar `__init__.py` em cada novo diretório

### 📦 Etapa 2: Extrair Utilitários (telegram_bot.py → domain/utils/)

#### 2.1 - time_utils.py (~150 linhas) ✅ CONCLUÍDO
- [x] `timeframe_to_minutes(timeframe: str) -> int`
- [x] `get_next_candle_start(now: datetime, timeframe: str) -> datetime`
- [x] `get_pre_alert_window_seconds(timeframe: str) -> Tuple[int, int]`
- [x] `get_higher_timeframe(timeframe: str) -> str`
- [x] `parse_monitor_duration_to_minutes(raw: str)`
- [x] `direction_cooldown_elapsed(...)` 
- [x] `_to_naive_utc(dt_value)`
- [x] `_extract_ticker_timestamp(ticker: dict)`
- [x] Commit: 35e8ade
- [ ] Testes manuais: /status, /analyze (fazer depois de integrar)

#### 2.2 - symbol_utils.py (~200 linhas)
- [ ] `resolve_market_symbol(symbol: str) -> tuple`
- [ ] `_normalize_crypto_symbol(asset: str) -> str`
- [ ] `_normalize_otc_symbol(symbol: str) -> str`
- [ ] `_is_price_parity_compatible(requested, market) -> bool`
- [ ] `_external_asset_group(asset: str) -> str`
- [ ] `_normalize_external_direction(raw_direction: str) -> str | None`
- [ ] Testes manuais: /analyze BTC, /analyze EURUSD

#### 2.3 - price_utils.py (~100 linhas)
- [ ] `resolve_reference_price(...) -> dict`
- [ ] `_to_float(value: str, default: float) -> float`
- [ ] `_safe_ratio(numerator, denominator, default) -> float`
- [ ] Testes manuais: /analyze com verificação de preços

#### 2.4 - config_utils.py (~80 linhas)
- [ ] `get_profile_env(base_key: str)`
- [ ] `_env_int(name: str, default: int, min_value: int) -> int`
- [ ] `_env_flag(raw_value: str | None, default: bool) -> bool`
- [ ] `_parse_external_allowlist(env_name: str, defaults: list) -> list`
- [ ] Testes manuais: bot startup, verificar env vars

### 🎯 Etapa 3: Criar Services de Domínio

#### 3.1 - signal_evaluator.py (~400 linhas)
- [ ] `evaluate_signal_setup(df, signal, signal_data, timeframe) -> dict`
- [ ] `_signal_quality_consensus(signal_data: dict, signal: int) -> int`
- [ ] `_three_candle_confirmation(df, signal) -> tuple`
- [ ] `_detect_sweep(df, signal, lookback) -> tuple`
- [ ] `is_false_breakout_risk(df, signal, timeframe) -> bool`
- [ ] `_last_fractal_level(df, direction)`
- [ ] Testes manuais: /analyze múltiplos ativos

#### 3.2 - liquidity_checker.py (~150 linhas)
- [ ] `_check_crypto_liquidity_session(asset: str) -> tuple[bool, str]`
- [ ] `_is_forex_session_active() -> tuple`
- [ ] `_get_crypto_signal_profile(asset: str) -> dict`
- [ ] Constantes: CRYPTO_TIER1_SYMBOLS, TIER2, TIER3
- [ ] Testes manuais: /analyze ADA (tier 3 fora de horário)

#### 3.3 - quality_gates.py (~100 linhas)
- [ ] `get_quality_gates(timeframe: str) -> dict`
- [ ] `get_setup_min_score(timeframe: str) -> int`
- [ ] `get_symbols_per_cycle(total_symbols, actionable_tfs) -> int`
- [ ] Testes manuais: /monitor start (verificar gates)

#### 3.4 - trend_analyzer.py (~80 linhas)
- [ ] `get_primary_trend(exchange, symbol, timeframe) -> int`
- [ ] `score_monitor_candidate(...) -> dict`
- [ ] `classify_binary_entry(...) -> str`
- [ ] Testes manuais: /analyze com trend analysis

#### 3.5 - weekend_analyzer.py (~200 linhas)
- [ ] `evaluate_weekend_binary_setup(...) -> tuple`
- [ ] `_count_range_touches(values, level, tolerance) -> int`
- [ ] `allow_weekend_reentry(...) -> bool`
- [ ] `reset_weekend_reentry_state(symbol_key)`
- [ ] `has_pending_martingale_decision(symbol_key, signal) -> bool`
- [ ] Testes manuais: /analyze no fim de semana

### 📱 Etapa 4: Separar Telegram Handlers

#### 4.1 - handlers/analyze_handler.py (~200 linhas)
- [ ] `async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE)`
- [ ] Lógica de parsing de argumentos
- [ ] Chamada aos services
- [ ] Formatação de resposta
- [ ] Testes manuais: /analyze, /analyze BTC, /analyze BTC 15m

#### 4.2 - handlers/monitor_handler.py (~800 linhas)
- [ ] `async def monitor_market(context: ContextTypes.DEFAULT_TYPE)`
- [ ] `async def monitor_start(update, context)`
- [ ] `async def monitor_stop(update, context)`
- [ ] `get_monitor_mode_label() -> str`
- [ ] `get_actionable_monitor_timeframes(now) -> list`
- [ ] `direction_cooldown_elapsed(...) -> bool`
- [ ] Testes manuais: /monitor start, verificar logs

#### 4.3 - handlers/status_handler.py (~150 linhas)
- [ ] `async def status(update, context)`
- [ ] `async def start(update, context)`
- [ ] `build_monitor_session_summary(reason) -> str`
- [ ] `get_operation_mode_snapshot(reference_time) -> dict`
- [ ] Testes manuais: /status, /start

#### 4.4 - handlers/config_handler.py (~100 linhas)
- [ ] `async def set_timeframe(update, context)`
- [ ] `async def toggle_monitor(update, context)`
- [ ] `_load_bot_state() -> dict`
- [ ] `_save_bot_state(key: str, value)`
- [ ] Testes manuais: /timeframe 5m, /togglemonitor

#### 4.5 - handlers/trading_handler.py (~200 linhas)
- [ ] `async def papertrade(update, context)`
- [ ] `async def scan_pending_trades(context)`
- [ ] `_get_scan_expiry_candle_close(pending) -> tuple`
- [ ] Testes manuais: /papertrade, verificar scan

#### 4.6 - handlers/external_signal_handler.py (~150 linhas)
- [ ] `async def pocket(update, context)`
- [ ] `async def tv(update, context)` (TradingView webhook)
- [ ] `_get_tv_analysis(asset, timeframe) -> dict`
- [ ] `_assess_signal_quality(...)`
- [ ] `_is_noise_scan_candidate(...) -> tuple`
- [ ] Testes manuais: /pocket com sinal formatado

#### 4.7 - handlers/calendar_handler.py (~80 linhas)
- [ ] `async def eco_events(update, context)`
- [ ] `async def eco_calendar_job(context)`
- [ ] Testes manuais: /eco

### 🎨 Etapa 5: Criar Formatters

#### 5.1 - formatters/signal_formatter.py (~150 linhas)
- [ ] `format_signal_message(signal_data: dict) -> str`
- [ ] `format_analysis_result(analysis: dict) -> str`
- [ ] `format_monitor_status(status: dict) -> str`
- [ ] Testes manuais: verificar formatação em /analyze

### 🔗 Etapa 6: Atualizar telegram_bot.py (Core)

#### 6.1 - Imports e Inicialização (~200 linhas)
- [ ] Importar novos módulos (utils, services, handlers)
- [ ] Manter apenas constantes globais essenciais
- [ ] Configuração de logging
- [ ] Instance lock

#### 6.2 - Main e Application Setup (~150 linhas)
- [ ] `def main()` - setup do bot
- [ ] Registro de handlers (importados de handlers/)
- [ ] Scheduler jobs
- [ ] `bootstrap_auto_monitoring()`
- [ ] Testes manuais: bot startup completo

#### 6.3 - Estado Global Mínimo (~100 linhas)
- [ ] `PENDING_BINARY_TRADES` - mantém global por simplicidade
- [ ] `LAST_SIGNAL_CACHE` - mantém global
- [ ] `_instance_lock_fd` - controle de instância única
- [ ] Funções auxiliares de lock: `acquire_instance_lock()`, `release_instance_lock()`

### ✅ Etapa 7: Testes e Validação

#### 7.1 - Testes Funcionais Manuais
- [ ] Bot startup sem erros
- [ ] /start - mensagem de boas-vindas
- [ ] /status - mostra configuração atual
- [ ] /analyze BTC - análise completa
- [ ] /analyze ADA - verifica tier 3 blocking
- [ ] /analyze EURUSD - teste forex (se aplicável)
- [ ] /monitor start - inicia monitoramento
- [ ] /monitor stop - para monitoramento
- [ ] /timeframe 15m - troca timeframe
- [ ] /papertrade - executa papel trade
- [ ] /eco - mostra calendário econômico
- [ ] /pocket - processa sinal externo

#### 7.2 - Verificações de Logs
- [ ] Nenhum erro de import
- [ ] Logs de ATLAS aparecem corretamente
- [ ] Tier system logando bloqueios
- [ ] Monitor loop funcionando

#### 7.3 - Comparação Before/After
- [ ] telegram_bot.py: 5.312 linhas → objetivo ~1.500 linhas
- [ ] Contagem final de arquivos criados
- [ ] Verificar nenhuma funcionalidade quebrada

### 📦 Etapa 8: Commits e Documentação

#### 8.1 - Commits Incrementais
- [ ] `feat(refactor): criar estrutura de diretórios fase 1`
- [ ] `feat(refactor): extrair time_utils e symbol_utils`
- [ ] `feat(refactor): extrair price_utils e config_utils`
- [ ] `feat(refactor): criar signal_evaluator service`
- [ ] `feat(refactor): criar liquidity_checker service`
- [ ] `feat(refactor): criar quality_gates e trend_analyzer`
- [ ] `feat(refactor): criar weekend_analyzer service`
- [ ] `feat(refactor): separar telegram handlers (analyze, monitor)`
- [ ] `feat(refactor): separar telegram handlers (status, config, trading)`
- [ ] `feat(refactor): separar telegram handlers (external, calendar)`
- [ ] `feat(refactor): criar signal formatters`
- [ ] `feat(refactor): limpar telegram_bot.py core (~1500 linhas)`
- [ ] `docs(refactor): atualizar README com nova estrutura`

#### 8.2 - Atualizar Documentação
- [ ] README.md - adicionar seção "Arquitetura"
- [ ] docs/ATLAS_TECNICO.md - documentar nova estrutura
- [ ] Este arquivo (REFATORACAO_FASE1.md) - marcar como concluído

---

## 📊 Métricas de Progresso

### Antes da Refatoração
```
telegram_bot.py: 5.312 linhas
Total funções globais: 63
Responsabilidades misturadas: ✅ Interface, ✅ Domínio, ✅ Infra
Testabilidade: 2/10
Manutenibilidade: 3/10
```

### Após Refatoração (Objetivo)
```
telegram_bot.py: ~1.500 linhas (apenas core + main)
Arquivos criados: ~18 novos módulos
Separação de responsabilidades: ✅ clara
Testabilidade: 6/10
Manutenibilidade: 7/10
```

---

## 🚨 Pontos de Atenção

### Estado Global Compartilhado
- `PENDING_BINARY_TRADES` - usado por múltiplos handlers
- `LAST_SIGNAL_CACHE` - usado por monitor e analyze
- **Solução:** Manter global na Fase 1, refatorar para classe State na Fase 2

### Circular Imports
- Handlers precisam acessar exchange/analyzer
- Services podem precisar de config
- **Solução:** Usar imports locais ou dependency injection light

### Compatibilidade com Scripts
- `run_bot_main.sh`, `run_bot_abbs_forex.sh`, `run_bot_otc.sh`
- **Garantir:** Mesmos imports em `telegram_bot.py` funcionam

---

## 🔄 Rollback Plan

Se algo quebrar:
```bash
# Voltar para versão anterior
git checkout main

# Ou reverter commits específicos
git revert <commit-hash>
```

**Backup:** Branch `feature/refactor-phase1` contém todo histórico incremental

---

## 📝 Notas de Execução

### [01/06/2026 - Início]
- Criado documento de planejamento
- Estrutura definida
- Pronto para começar extração

### [Próximas Atualizações]
- Registrar aqui cada etapa concluída
- Problemas encontrados
- Soluções aplicadas
- Tempo real gasto

---

## ✅ Critérios de Sucesso

1. ✅ Bot inicia sem erros
2. ✅ Todos os comandos funcionando (/analyze, /monitor, /status, etc.)
3. ✅ Nenhuma regressão funcional
4. ✅ telegram_bot.py < 2.000 linhas
5. ✅ Código mais organizado e legível
6. ✅ Logs de ATLAS funcionando corretamente
7. ✅ Sistema de tiers funcionando (ADA bloqueado fora de horário)
8. ✅ Documentação atualizada

---

**Próximo Passo:** Criar branch e começar Etapa 1 (estrutura de diretórios)
