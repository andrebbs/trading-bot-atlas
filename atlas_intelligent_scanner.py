# -*- coding: utf-8 -*-
"""
ATLAS Intelligent Scanner
=========================
Módulo autônomo para varredura periódica de ativos com base
no sistema de pontuação Confluence (ConfluenceScoreSystem).

Comandos Telegram disponíveis após registro:
  /scanner on                        – ativa o scanner
  /scanner off                       – desativa o scanner
  /scanner status                    – exibe estado atual
  /scanner intervalo <minutos>       – altera intervalo (mín. 1)
  /scanner ativos BTC/USDT,ETH/USDT  – define lista de ativos
  /scanner timeframe 5m              – define timeframe
  /scanner score 0.65                – define score mínimo
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("atlas.scanner")

# ─── Tentativa de importar CommandHandler do python-telegram-bot ───
try:
    from telegram.ext import CommandHandler
    _TELEGRAM_OK = True
except ImportError:
    CommandHandler = None          # type: ignore
    _TELEGRAM_OK = False
    logger.warning("python-telegram-bot não instalado – modo standalone ativo.")


# ══════════════════════════════════════════════
#  ESTADO GLOBAL DO SCANNER
# ══════════════════════════════════════════════
SCANNER_STATE: Dict[str, Any] = {
    # Liga/desliga
    "enabled": os.getenv("ATLAS_SCANNER_ENABLED", "false").lower()
               in ("1", "true", "yes", "on"),

    # Intervalo em segundos (padrão: 5 min)
    "interval": int(os.getenv("ATLAS_SCANNER_INTERVAL_SECONDS", "300")),

    # Timeframe padrão
    "timeframe": os.getenv("ATLAS_SCANNER_TIMEFRAME", "5m"),

    # Ativos monitorados
    "symbols": [
        s.strip()
        for s in os.getenv(
            "ATLAS_SCANNER_SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT"
        ).split(",")
        if s.strip()
    ],

    # Score mínimo para disparo de alerta
    "min_score": float(os.getenv("ATLAS_SCANNER_MIN_SCORE", "0.58")),

    # Cooldown entre alertas do mesmo ativo/sinal (segundos)
    "cooldown_seconds": int(
        os.getenv("ATLAS_SCANNER_COOLDOWN_SECONDS", "900")
    ),

    # Registro interno dos últimos alertas {chave: timestamp}
    "last_alert": {},
}


# ══════════════════════════════════════════════
#  FUNÇÕES UTILITÁRIAS
# ══════════════════════════════════════════════

def _now_utc() -> datetime:
    """Retorna datetime UTC-aware."""
    return datetime.now(tz=timezone.utc)


def _now_str() -> str:
    """Retorna string formatada do horário UTC."""
    return _now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")


# ══════════════════════════════════════════════
#  INTEGRAÇÃO COM ConfluenceScoreSystem
# ══════════════════════════════════════════════

def _load_confluence_class() -> Optional[type]:
    """
    Tenta importar ConfluenceScoreSystem de vários caminhos possíveis.
    Retorna a classe ou None se não encontrada.
    """
    candidates = [
        ("src.core.confluence_score", "ConfluenceScoreSystem"),
        ("core.confluence_score",     "ConfluenceScoreSystem"),
        ("confluence_score",          "ConfluenceScoreSystem"),
        ("src.analysis.confluence",   "ConfluenceScoreSystem"),
    ]
    for module_path, class_name in candidates:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name, None)
            if cls is not None:
                logger.debug("ConfluenceScoreSystem carregada de %s", module_path)
                return cls
        except (ImportError, ModuleNotFoundError):
            continue
    return None


_CONFLUENCE_CLS = None   # cache da classe


def _get_confluence_class() -> Optional[type]:
    global _CONFLUENCE_CLS
    if _CONFLUENCE_CLS is None:
        _CONFLUENCE_CLS = _load_confluence_class()
    return _CONFLUENCE_CLS


def _normalize_result(symbol: str, raw: Any) -> Dict[str, Any]:
    """
    Normaliza o retorno do ConfluenceScoreSystem para um dict padrão:
      { symbol, score, signal, confidence, valid, ... }
    Funciona com dict, objeto ou None.
    """
    base: Dict[str, Any] = {
        "symbol":     symbol,
        "score":      0.0,
        "signal":     "NEUTRAL",
        "confidence": 0.0,
        "valid":      False,
    }

    if raw is None:
        return base

    # ── dict ──
    if isinstance(raw, dict):
        score  = float(raw.get("score",
                  raw.get("confluence_score",
                  raw.get("total_score", 0))) or 0)
        signal = str(raw.get("signal",
                  raw.get("direction",
                  raw.get("recommendation", "NEUTRAL")))).upper()
        conf   = float(raw.get("confidence",
                  raw.get("probability", score)) or 0)
        valid  = bool(raw.get("valid",
                  raw.get("should_trade",
                  raw.get("should_enter", False))))

        # Forçar valid se sinal forte + score suficiente
        strong = {"BUY","LONG","CALL","BULLISH","SELL","SHORT","PUT","BEARISH"}
        if signal in strong and score >= float(SCANNER_STATE["min_score"]):
            valid = True

        return {**raw, "symbol": symbol, "score": score,
                "signal": signal, "confidence": conf, "valid": valid}

    # ── objeto ──
    score  = float(getattr(raw, "score",
               getattr(raw, "confluence_score", 0)) or 0)
    signal = str(getattr(raw, "signal",
               getattr(raw, "direction", "NEUTRAL"))).upper()
    conf   = float(getattr(raw, "confidence", score) or 0)
    valid  = bool(getattr(raw, "valid",
               getattr(raw, "should_trade", False)))

    return {"symbol": symbol, "score": score,
            "signal": signal, "confidence": conf, "valid": valid, "_raw": raw}


def _run_analysis(symbol: str, timeframe: str) -> Dict[str, Any]:
    """
    Executa análise de confluência para um ativo.
    Compatível com diferentes assinaturas de método.
    """
    cls = _get_confluence_class()
    if cls is None:
        return {
            "symbol": symbol, "score": 0.0, "signal": "NO_ENGINE",
            "confidence": 0.0, "valid": False,
            "error": "ConfluenceScoreSystem não encontrada no projeto",
        }

    try:
        system = cls()
        # Tenta métodos mais comuns
        for method_name in ("analyze", "analyze_symbol",
                            "calculate", "get_signal", "run"):
            method = getattr(system, method_name, None)
            if not callable(method):
                continue
            try:
                raw = method(symbol=symbol, timeframe=timeframe)
            except TypeError:
                try:
                    raw = method(symbol, timeframe)
                except TypeError:
                    raw = method(symbol)
            return _normalize_result(symbol, raw)

        return {**_normalize_result(symbol, None),
                "error": "Nenhum método compatível encontrado"}

    except Exception as exc:
        logger.exception("Erro ao analisar %s", symbol)
        return {**_normalize_result(symbol, None),
                "signal": "ERROR", "error": str(exc)}


# ══════════════════════════════════════════════
#  LÓGICA DE ALERTA (cooldown)
# ══════════════════════════════════════════════

def _should_alert(result: Dict[str, Any]) -> bool:
    """
    Retorna True se o resultado merece um alerta Telegram agora,
    respeitando score mínimo e cooldown.
    """
    symbol = result.get("symbol", "")
    score  = float(result.get("score", 0) or 0)
    signal = str(result.get("signal", "NEUTRAL")).upper()

    # Sem sinal válido
    if not result.get("valid") or score < float(SCANNER_STATE["min_score"]):
        return False

    # Sinais fracos ou inúteis
    skip = {"NEUTRAL", "WEAK", "ERROR", "NONE", "WAIT",
            "NO_ENGINE", "HOLD", "INDEFINIDO"}
    if signal in skip:
        return False

    # Cooldown
    key  = f"{symbol}:{signal}"
    now  = _now_utc().timestamp()
    last = SCANNER_STATE["last_alert"].get(key, 0)
    if now - last < int(SCANNER_STATE["cooldown_seconds"]):
        logger.debug("Cooldown ativo para %s – ignorando.", key)
        return False

    SCANNER_STATE["last_alert"][key] = now
    return True


def _format_alert(result: Dict[str, Any]) -> str:
    """Formata mensagem de alerta para o Telegram."""
    emoji = "🟢" if result.get("signal","").upper() in (
        "BUY","LONG","CALL","BULLISH") else "🔴"
    return (
        f"🔥 *ATLAS SCANNER – ALERTA*
"
        f"{emoji} *Ativo:* `{result.get('symbol')}`
"
        f"📊 *Sinal:* `{result.get('signal')}`
"
        f"🏆 *Score:* `{float(result.get('score', 0) or 0):.2f}`
"
        f"🎯 *Confiança:* `{float(result.get('confidence', 0) or 0):.2f}`
"
        f"⏱ *Timeframe:* `{SCANNER_STATE.get('timeframe')}`
"
        f"🕐 *Horário:* `{_now_str()}`"
    )


# ══════════════════════════════════════════════
#  JOB PERIÓDICO (python-telegram-bot JobQueue)
# ══════════════════════════════════════════════

async def atlas_scanner_job(context) -> None:
    """
    Executado automaticamente pelo JobQueue.
    Analisa todos os ativos e envia alertas se necessário.
    """
    if not SCANNER_STATE.get("enabled"):
        return

    # Obtém chat_id para envio
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    tf      = SCANNER_STATE.get("timeframe", "5m")

    for symbol in list(SCANNER_STATE.get("symbols", [])):
        result = _run_analysis(symbol, tf)
        logger.info(
            "Scanner – %s | signal=%s | score=%.2f | valid=%s",
            symbol, result.get("signal"), result.get("score", 0),
            result.get("valid"),
        )
        if _should_alert(result) and chat_id:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=_format_alert(result),
                    parse_mode="Markdown",
                )
            except Exception as exc:
                logger.error("Falha ao enviar alerta para %s: %s", symbol, exc)


# ══════════════════════════════════════════════
#  COMANDO /scanner  (handler Telegram)
# ══════════════════════════════════════════════

async def scanner_command(update, context) -> None:
    """
    Handler do comando /scanner.
    Subcomandos: on | off | status | intervalo | ativos | timeframe | score
    """
    args = [a.lower() for a in (getattr(context, "args", []) or [])]
    reply = update.message.reply_text

    # ── sem args ou 'status' ──────────────────
    if not args or args[0] in ("status", "estado"):
        estado = "ON ✅" if SCANNER_STATE["enabled"] else "OFF ❌"
        await reply(
            f"*ATLAS Scanner Status*
"
            f"Estado: {estado}
"
            f"Intervalo: {SCANNER_STATE['interval']}s "
            f"({SCANNER_STATE['interval']//60} min)
"
            f"Timeframe: {SCANNER_STATE['timeframe']}
"
            f"Score mínimo: {SCANNER_STATE['min_score']}
"
            f"Ativos: {', '.join(SCANNER_STATE['symbols'])}
"
            f"Cooldown: {SCANNER_STATE['cooldown_seconds']}s",
            parse_mode="Markdown",
        )
        return

    # ── on ───────────────────────────────────
    if args[0] == "on":
        SCANNER_STATE["enabled"] = True
        await reply("✅ Scanner Inteligente ATLAS *ativado*.", parse_mode="Markdown")
        return

    # ── off ──────────────────────────────────
    if args[0] == "off":
        SCANNER_STATE["enabled"] = False
        await reply("⛔ Scanner Inteligente ATLAS *desativado*.", parse_mode="Markdown")
        return

    # ── intervalo <minutos> ───────────────────
    if args[0] in ("intervalo", "interval", "tempo") and len(args) >= 2:
        try:
            minutes = max(1, int(args[1]))
        except ValueError:
            await reply("❌ Use: /scanner intervalo <número de minutos>")
            return

        SCANNER_STATE["interval"] = minutes * 60

        # Re-agenda o job se o JobQueue estiver disponível
        jq = getattr(getattr(context, "application", None), "job_queue", None)
        if jq:
            for job in jq.get_jobs_by_name("atlas_scanner_job"):
                job.schedule_removal()
            jq.run_repeating(
                atlas_scanner_job,
                interval=SCANNER_STATE["interval"],
                first=5,
                name="atlas_scanner_job",
            )

        await reply(
            f"⏱ Intervalo ajustado para *{minutes} min*.",
            parse_mode="Markdown",
        )
        return

    # ── ativos ───────────────────────────────
    if args[0] in ("symbols", "ativos", "pares") and len(args) >= 2:
        raw_syms = " ".join(args[1:])
        syms = [s.strip().upper()
                for s in raw_syms.replace(",", " ").split()
                if s.strip()]
        if not syms:
            await reply("❌ Informe ao menos um ativo. Ex: /scanner ativos BTC/USDT,ETH/USDT")
            return
        SCANNER_STATE["symbols"] = syms
        await reply(
            f"✅ Ativos atualizados: `{', '.join(syms)}`",
            parse_mode="Markdown",
        )
        return

    # ── timeframe ────────────────────────────
    if args[0] in ("tf", "timeframe") and len(args) >= 2:
        SCANNER_STATE["timeframe"] = args[1]
        await reply(
            f"✅ Timeframe atualizado: `{args[1]}`",
            parse_mode="Markdown",
        )
        return

    # ── score mínimo ─────────────────────────
    if args[0] in ("score", "minscore", "min") and len(args) >= 2:
        try:
            sc = float(args[1])
            if not (0.0 <= sc <= 1.0):
                raise ValueError
        except ValueError:
            await reply("❌ Score deve ser um número entre 0.0 e 1.0. Ex: /scanner score 0.65")
            return
        SCANNER_STATE["min_score"] = sc
        await reply(
            f"✅ Score mínimo atualizado: `{sc}`",
            parse_mode="Markdown",
        )
        return

    # ── ajuda ────────────────────────────────
    await reply(
        "ℹ️ *Comandos do Scanner ATLAS*
"
        "/scanner on
"
        "/scanner off
"
        "/scanner status
"
        "/scanner intervalo 5
"
        "/scanner ativos BTC/USDT,ETH/USDT,SOL/USDT
"
        "/scanner timeframe 5m
"
        "/scanner score 0.65",
        parse_mode="Markdown",
    )


# ══════════════════════════════════════════════
#  REGISTRO NO APPLICATION
# ══════════════════════════════════════════════

def register_atlas_scanner(application) -> None:
    """
    Registra o Scanner Inteligente no Application do python-telegram-bot.

    Uso no seu main / telegram_bot.py:
        from atlas_intelligent_scanner import register_atlas_scanner
        ...
        app = Application.builder().token(TOKEN).build()
        register_atlas_scanner(app)
        app.run_polling()
    """
    if not _TELEGRAM_OK:
        logger.error(
            "python-telegram-bot não está instalado. "
            "Scanner não registrado."
        )
        return

    # Registra handler do comando
    application.add_handler(CommandHandler("scanner", scanner_command))

    # Agenda job periódico se JobQueue disponível
    jq = getattr(application, "job_queue", None)
    if jq:
        jq.run_repeating(
            atlas_scanner_job,
            interval=SCANNER_STATE["interval"],
            first=10,
            name="atlas_scanner_job",
        )
        logger.info(
            "Scanner Inteligente ATLAS registrado – intervalo=%ss, ativos=%s",
            SCANNER_STATE["interval"],
            SCANNER_STATE["symbols"],
        )
    else:
        logger.warning(
            "JobQueue não disponível. "
            "Instale python-telegram-bot[job-queue] para varredura automática."
        )
