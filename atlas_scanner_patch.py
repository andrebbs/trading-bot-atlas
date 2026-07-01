# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict

try:
    from telegram.ext import CommandHandler
except Exception:
    CommandHandler = None

SCANNER_STATE: Dict[str, Any] = {
    "enabled": os.getenv("ATLAS_SCANNER_ENABLED", "false").lower() in ("1", "true", "yes", "on"),
    "interval": int(os.getenv("ATLAS_SCANNER_INTERVAL_SECONDS", "300")),
    "timeframe": os.getenv("ATLAS_SCANNER_TIMEFRAME", "5m"),
    "symbols": [s.strip() for s in os.getenv("ATLAS_SCANNER_SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT").split(",") if s.strip()],
    "min_score": float(os.getenv("ATLAS_SCANNER_MIN_SCORE", "0.58")),
    "last_alert": {},
    "cooldown_seconds": int(os.getenv("ATLAS_SCANNER_COOLDOWN_SECONDS", "900")),
}

def _now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

def _normalize_confluence_result(symbol: str, raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {"symbol": symbol, "score": 0.0, "signal": "NEUTRAL", "confidence": 0.0, "valid": False}
    if isinstance(raw, dict):
        score = float(raw.get("score", raw.get("confluence_score", raw.get("total_score", 0))) or 0)
        signal = str(raw.get("signal", raw.get("direction", raw.get("recommendation", "NEUTRAL")))).upper()
        confidence = float(raw.get("confidence", raw.get("probability", score)) or 0)
        valid = bool(raw.get("valid", raw.get("should_trade", raw.get("should_enter", False))))
        if signal in ("BUY","LONG","CALL","BULLISH","SELL","SHORT","PUT","BEARISH") and score >= SCANNER_STATE["min_score"]:
            valid = True
        return {**raw, "symbol": symbol, "score": score, "signal": signal, "confidence": confidence, "valid": valid}
    score = float(getattr(raw, "score", getattr(raw, "confluence_score", 0)) or 0)
    signal = str(getattr(raw, "signal", getattr(raw, "direction", "NEUTRAL"))).upper()
    confidence = float(getattr(raw, "confidence", score) or 0)
    valid = bool(getattr(raw, "valid", getattr(raw, "should_trade", False)))
    return {"symbol": symbol, "score": score, "signal": signal, "confidence": confidence, "valid": valid, "raw": raw}

def _run_confluence_analysis(symbol: str, timeframe: str = "5m") -> Dict[str, Any]:
    try:
        cls = globals().get("ConfluenceScoreSystem")
        if cls is None:
            from src.core.confluence_score import ConfluenceScoreSystem as cls
        system = cls()
        for method_name in ("analyze", "analyze_symbol", "calculate", "get_signal"):
            method = getattr(system, method_name, None)
            if callable(method):
                try:
                    raw = method(symbol=symbol, timeframe=timeframe)
                except TypeError:
                    raw = method(symbol, timeframe)
                return _normalize_confluence_result(symbol, raw)
        return {"symbol": symbol, "score": 0.0, "signal": "NEUTRAL", "confidence": 0.0, "valid": False, "error": "No compatible method"}
    except Exception as e:
        return {"symbol": symbol, "score": 0.0, "signal": "ERROR", "confidence": 0.0, "valid": False, "error": str(e)}

def _scanner_should_alert(result: Dict[str, Any]) -> bool:
    symbol = result.get("symbol", "")
    score = float(result.get("score", 0) or 0)
    signal = str(result.get("signal", "NEUTRAL")).upper()
    if not result.get("valid") or score < float(SCANNER_STATE["min_score"]):
        return False
    if signal in ("NEUTRAL", "WEAK", "ERROR", "NONE", "WAIT"):
        return False
    now = datetime.utcnow().timestamp()
    key = f"{symbol}:{signal}"
    last = SCANNER_STATE["last_alert"].get(key, 0)
    if now - last < int(SCANNER_STATE["cooldown_seconds"]):
        return False
    SCANNER_STATE["last_alert"][key] = now
    return True

def _format_scanner_alert(result: Dict[str, Any]) -> str:
    return (
        "🔥 ATLAS SCANNER ALERT\n"
        f"Ativo: {result.get('symbol')}\n"
        f"Sinal: {result.get('signal')}\n"
        f"Score: {float(result.get('score', 0) or 0):.2f}\n"
        f"Confiança: {float(result.get('confidence', 0) or 0):.2f}\n"
        f"Timeframe: {SCANNER_STATE.get('timeframe')}\n"
        f"Horário: {_now_str()}"
    )

async def atlas_scanner_job(context) -> None:
    if not SCANNER_STATE.get("enabled"):
        return
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    for symbol in list(SCANNER_STATE.get("symbols", [])):
        result = _run_confluence_analysis(symbol, SCANNER_STATE.get("timeframe", "5m"))
        if _scanner_should_alert(result) and chat_id:
            await context.bot.send_message(chat_id=chat_id, text=_format_scanner_alert(result))

async def scanner_command(update, context):
    args = [a.lower() for a in getattr(context, "args", [])]
    if not args or args[0] == "status":
        status = "ON ✅" if SCANNER_STATE["enabled"] else "OFF ❌"
        await update.message.reply_text(
            f"Scanner: {status}\nIntervalo: {SCANNER_STATE['interval']}s\n"
            f"Timeframe: {SCANNER_STATE['timeframe']}\nMin score: {SCANNER_STATE['min_score']}\n"
            f"Ativos: {', '.join(SCANNER_STATE['symbols'])}"
        )
    elif args[0] == "on":
        SCANNER_STATE["enabled"] = True
        await update.message.reply_text("✅ Scanner Inteligente ATLAS ativado")
    elif args[0] == "off":
        SCANNER_STATE["enabled"] = False
        await update.message.reply_text("⛔ Scanner Inteligente ATLAS desativado")
    elif args[0] in ("intervalo", "interval", "tempo") and len(args) >= 2:
        minutes = max(1, int(args[1]))
        SCANNER_STATE["interval"] = minutes * 60
        jq = getattr(context.application, "job_queue", None)
        if jq:
            for job in jq.get_jobs_by_name("atlas_scanner_job"):
                job.schedule_removal()
            jq.run_repeating(atlas_scanner_job, interval=SCANNER_STATE["interval"], first=5, name="atlas_scanner_job")
        await update.message.reply_text(f"⏱ Intervalo ajustado para {minutes} min")
    elif args[0] in ("symbols", "ativos") and len(args) >= 2:
        syms = []
        for raw in args[1:]:
            syms.extend([x.strip().upper() for x in raw.split(",") if x.strip()])
        SCANNER_STATE["symbols"] = syms
        await update.message.reply_text(f"✅ Ativos atualizados: {', '.join(syms)}")
    elif args[0] in ("tf", "timeframe") and len(args) >= 2:
        SCANNER_STATE["timeframe"] = args[1]
        await update.message.reply_text(f"✅ Timeframe atualizado: {args[1]}")
    else:
        await update.message.reply_text(
            "Comandos:\n/scanner on\n/scanner off\n/scanner status\n"
            "/scanner intervalo 5\n/scanner ativos BTC/USDT,ETH/USDT\n/scanner timeframe 5m"
        )

def register_atlas_scanner(application) -> None:
    if CommandHandler is not None:
        application.add_handler(CommandHandler("scanner", scanner_command))
    jq = getattr(application, "job_queue", None)
    if jq:
        jq.run_repeating(atlas_scanner_job, interval=SCANNER_STATE["interval"], first=10, name="atlas_scanner_job")
