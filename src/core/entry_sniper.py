"""
Entry Sniper — ATLAS v2 INSTITUCIONAL
src/core/entry_sniper.py

Módulo de gatilho final de entrada.

Fluxo obrigatório para entrada:
  1. Liquidity Sweep confirmado (caçada de stops)
  2. BOS ou CHoCH após o sweep (confirmação de reversão)
  3. Retorno ao Order Block ou FVG (pullback institucional)
  4. Confirmação de Price Action no pullback
  5. Cálculo de Entry / Stop Loss / Take Profit institucionais

Resultado:
  - entry_price  : ponto exato de entrada
  - stop_loss    : abaixo/acima do swing capturado (sweep)
  - take_profit  : próxima zona de liquidez oposta
  - risk_reward  : RR calculado (mínimo 1:2)
  - quality      : PREMIUM | STANDARD | REJECT
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Tuple, List

from src.core.smc_detector import SMCDetector
from src.core.price_action_detector import PriceActionDetector

logger = logging.getLogger(__name__)


class EntrySniper:
    """
    Gatilho de entrada institucional ATLAS v2.

    Uso:
        sniper  = EntrySniper()
        result  = sniper.find_entry(df, direction="BUY")

        if result["valid"]:
            entry  = result["entry_price"]
            sl     = result["stop_loss"]
            tp     = result["take_profit"]
            rr     = result["risk_reward"]
    """

    MIN_RR           = 2.0    # RR mínimo aceitável
    PREMIUM_RR       = 3.0    # RR para qualidade PREMIUM
    OB_TOLERANCE     = 0.003  # 0.3% tolerância ao redor do OB
    FVG_TOLERANCE    = 0.003
    SL_BUFFER        = 0.002  # buffer acima/abaixo do sweep (0.2%)

    def __init__(self):
        self.smc = SMCDetector()
        self.pa  = PriceActionDetector()

    # ──────────────────────────────────────────────────────────────
    # VERIFICAÇÃO DE PRÉ-CONDIÇÕES (SWEEP + BOS/CHOCH)
    # ──────────────────────────────────────────────────────────────
    def _check_preconditions(self, df: pd.DataFrame, direction: str) -> Tuple[bool, str, Dict]:
        """
        Verifica se o setup SMC está completo antes de buscar entrada.
        Retorna (válido, motivo, dados_smc).
        """
        analysis = self.smc.get_analysis(df)
        sweep    = analysis["liquidity_sweep"]
        bos      = analysis["bos"]
        choch    = analysis["choch"]
        structure = analysis["structure"]

        # Sem setup → rejeitar
        if not analysis["has_setup"]:
            return False, "Sem setup SMC (falta sweep + BOS/CHoCH)", analysis

        if direction == "BUY":
            # Precisa de sweep de LOW + confirmação bullish
            if not sweep["swept_low"]:
                return False, "Sem sweep de liquidez bearish (falta caçada de stops)", analysis
            if not (bos["bullish_bos"] or choch["bullish_choch"]):
                return False, "Sem BOS/CHoCH bullish após sweep", analysis
            if structure == "bearish":
                return False, "Estrutura macro bearish — contra o setup", analysis

        else:  # SELL
            if not sweep["swept_high"]:
                return False, "Sem sweep de liquidez bullish (falta caçada de stops)", analysis
            if not (bos["bearish_bos"] or choch["bearish_choch"]):
                return False, "Sem BOS/CHoCH bearish após sweep", analysis
            if structure == "bullish":
                return False, "Estrutura macro bullish — contra o setup", analysis

        return True, "Setup SMC confirmado", analysis

    # ──────────────────────────────────────────────────────────────
    # BUSCA DE ZONA DE ENTRADA (OB ou FVG)
    # ──────────────────────────────────────────────────────────────
    def _find_entry_zone(self, df: pd.DataFrame, direction: str,
                         smc_data: Dict) -> Optional[Dict]:
        """
        Busca o melhor Order Block ou FVG para entrada de pullback.
        Prioridade: OB > FVG (OB é mais forte institucionalmente).
        """
        obs  = smc_data["order_blocks"]
        fvgs = smc_data["fvgs"]
        last_close = float(df.iloc[-1]["close"])

        if direction == "BUY":
            # Busca OB bullish ativo próximo abaixo do preço atual
            for ob in reversed(obs["bullish"]):
                zone_high = ob["high"] * (1 + self.OB_TOLERANCE)
                zone_low  = ob["low"]  * (1 - self.OB_TOLERANCE)
                if zone_low <= last_close <= zone_high:
                    return {
                        "type":   "ORDER_BLOCK",
                        "entry":  (ob["high"] + ob["low"]) / 2,
                        "top":    ob["high"],
                        "bottom": ob["low"],
                        "strength": "STRONG",
                    }

            # Fallback: FVG bullish
            for fvg in reversed(fvgs["bullish"]):
                if fvg["bottom"] <= last_close <= fvg["top"] * (1 + self.FVG_TOLERANCE):
                    return {
                        "type":   "FVG",
                        "entry":  fvg["mid"],
                        "top":    fvg["top"],
                        "bottom": fvg["bottom"],
                        "strength": "MODERATE",
                    }

        else:  # SELL
            for ob in reversed(obs["bearish"]):
                zone_high = ob["high"] * (1 + self.OB_TOLERANCE)
                zone_low  = ob["low"]  * (1 - self.OB_TOLERANCE)
                if zone_low <= last_close <= zone_high:
                    return {
                        "type":   "ORDER_BLOCK",
                        "entry":  (ob["high"] + ob["low"]) / 2,
                        "top":    ob["high"],
                        "bottom": ob["low"],
                        "strength": "STRONG",
                    }

            for fvg in reversed(fvgs["bearish"]):
                if fvg["bottom"] * (1 - self.FVG_TOLERANCE) <= last_close <= fvg["top"]:
                    return {
                        "type":   "FVG",
                        "entry":  fvg["mid"],
                        "top":    fvg["top"],
                        "bottom": fvg["bottom"],
                        "strength": "MODERATE",
                    }

        return None

    # ──────────────────────────────────────────────────────────────
    # CÁLCULO DE STOP LOSS INSTITUCIONAL
    # ──────────────────────────────────────────────────────────────
    def _calculate_stop_loss(self, df: pd.DataFrame, direction: str,
                              sweep: Dict) -> float:
        """
        Stop Loss institucional:
        - BUY : abaixo do nível do sweep de low (+ buffer)
        - SELL: acima do nível do sweep de high (+ buffer)
        """
        last_close = float(df.iloc[-1]["close"])

        if sweep.get("sweep_level") is not None:
            level = float(sweep["sweep_level"])
            if direction == "BUY":
                return level * (1 - self.SL_BUFFER)
            else:
                return level * (1 + self.SL_BUFFER)

        # Fallback: swing recente
        window = min(20, len(df))
        if direction == "BUY":
            return float(df["low"].tail(window).min()) * (1 - self.SL_BUFFER)
        else:
            return float(df["high"].tail(window).max()) * (1 + self.SL_BUFFER)

    # ──────────────────────────────────────────────────────────────
    # CÁLCULO DE TAKE PROFIT (NEXT LIQUIDITY)
    # ──────────────────────────────────────────────────────────────
    def _calculate_take_profit(self, df: pd.DataFrame, direction: str,
                                entry: float, stop_loss: float,
                                smc_data: Dict) -> Tuple[float, float]:
        """
        Take Profit na próxima zona de liquidez oposta.
        Garante RR >= MIN_RR.
        Returns (take_profit, risk_reward)
        """
        risk    = abs(entry - stop_loss)
        min_tp  = entry + risk * self.MIN_RR if direction == "BUY" else entry - risk * self.MIN_RR

        sweep      = smc_data["liquidity_sweep"]
        equal_h    = sweep.get("equal_highs", [])
        equal_l    = sweep.get("equal_lows",  [])

        if direction == "BUY":
            # TP na próxima liquidez de high acima do entry
            targets = sorted([h for h in equal_h if h > entry * 1.005])
            if targets:
                tp = targets[0]
                if tp < min_tp:
                    tp = min_tp
            else:
                tp = min_tp
        else:
            targets = sorted([l for l in equal_l if l < entry * 0.995], reverse=True)
            if targets:
                tp = targets[0]
                if tp > min_tp:
                    tp = min_tp
            else:
                tp = min_tp

        rr = abs(tp - entry) / risk if risk > 0 else 0
        return tp, rr

    # ──────────────────────────────────────────────────────────────
    # CONFIRMAÇÃO DE PRICE ACTION NA ZONA
    # ──────────────────────────────────────────────────────────────
    def _confirm_price_action(self, df: pd.DataFrame, direction: str) -> Dict:
        """
        Confirma que o price action atual suporta entrada.
        Retorna score e padrão encontrado.
        """
        pa_score = self.pa.get_price_action_score(df, direction)
        pa_data  = self.pa.get_analysis(df)

        if direction == "BUY":
            pattern = (
                "PIN_BAR" if pa_data.get("pin_bar_bullish") else
                "ENGULFING" if pa_data.get("bullish_engulfing") else
                "MOMENTUM" if pa_data.get("momentum_buy") else
                "NONE"
            )
        else:
            pattern = (
                "PIN_BAR" if pa_data.get("pin_bar_bearish") else
                "ENGULFING" if pa_data.get("bearish_engulfing") else
                "MOMENTUM" if pa_data.get("momentum_sell") else
                "NONE"
            )

        return {
            "score":   pa_score,
            "pattern": pattern,
            "valid":   pa_score >= 0.55 and not pa_data.get("is_doji", False),
        }

    # ──────────────────────────────────────────────────────────────
    # FIND ENTRY — MÉTODO PRINCIPAL
    # ──────────────────────────────────────────────────────────────
    def find_entry(self, df: pd.DataFrame, direction: str) -> Dict:
        """
        Busca entrada institucional completa.

        Returns dict com:
          valid         : bool
          entry_price   : float
          stop_loss     : float
          take_profit   : float
          risk_reward   : float
          quality       : PREMIUM | STANDARD | REJECT
          zone_type     : ORDER_BLOCK | FVG
          pa_pattern    : PIN_BAR | ENGULFING | MOMENTUM | NONE
          reject_reason : str (se não válido)
        """
        base = {
            "valid": False, "entry_price": None,
            "stop_loss": None, "take_profit": None,
            "risk_reward": 0, "quality": "REJECT",
            "zone_type": None, "pa_pattern": None,
            "reject_reason": None,
        }

        try:
            if len(df) < 30:
                base["reject_reason"] = "Dados insuficientes (< 30 candles)"
                return base

            # ── 1. PRÉ-CONDIÇÕES SMC ───────────────────────────
            ok, reason, smc_data = self._check_preconditions(df, direction)
            if not ok:
                base["reject_reason"] = reason
                return base

            # ── 2. ZONA DE ENTRADA (OB/FVG) ───────────────────
            zone = self._find_entry_zone(df, direction, smc_data)
            if zone is None:
                base["reject_reason"] = "Preço não está em OB/FVG válido"
                return base

            # ── 3. CONFIRMAÇÃO PRICE ACTION ───────────────────
            pa = self._confirm_price_action(df, direction)
            if not pa["valid"]:
                base["reject_reason"] = f"Price Action fraco ({pa['pattern']}) — aguardar"
                return base

            # ── 4. STOP LOSS ──────────────────────────────────
            sweep = smc_data["liquidity_sweep"]
            sl    = self._calculate_stop_loss(df, direction, sweep)
            entry = zone["entry"]

            # Garantia: SL faz sentido
            if direction == "BUY" and sl >= entry:
                base["reject_reason"] = "SL acima do entry — geometria inválida"
                return base
            if direction == "SELL" and sl <= entry:
                base["reject_reason"] = "SL abaixo do entry — geometria inválida"
                return base

            # ── 5. TAKE PROFIT + RR ───────────────────────────
            tp, rr = self._calculate_take_profit(df, direction, entry, sl, smc_data)

            if rr < self.MIN_RR:
                base["reject_reason"] = f"RR insuficiente ({rr:.2f} < {self.MIN_RR})"
                return base

            # ── 6. QUALIDADE ──────────────────────────────────
            choch_ok = (
                smc_data["choch"]["bullish_choch"] if direction == "BUY"
                else smc_data["choch"]["bearish_choch"]
            )
            ob_zone   = zone["type"] == "ORDER_BLOCK"
            pin_bar   = pa["pattern"] == "PIN_BAR"

            if choch_ok and ob_zone and rr >= self.PREMIUM_RR:
                quality = "PREMIUM"
            elif rr >= self.MIN_RR and (ob_zone or pin_bar):
                quality = "STANDARD"
            else:
                quality = "STANDARD"

            # ── 7. RESULTADO FINAL ────────────────────────────
            return {
                "valid":        True,
                "direction":    direction,
                "entry_price":  round(entry, 8),
                "stop_loss":    round(sl, 8),
                "take_profit":  round(tp, 8),
                "risk_reward":  round(rr, 2),
                "quality":      quality,
                "zone_type":    zone["type"],
                "zone_strength": zone["strength"],
                "pa_pattern":   pa["pattern"],
                "pa_score":     round(pa["score"], 4),
                "choch":        choch_ok,
                "sweep_level":  sweep.get("sweep_level"),
                "reject_reason": None,
            }

        except Exception as e:
            logger.error(f"Erro EntrySniper.find_entry: {e}")
            base["reject_reason"] = f"Erro interno: {str(e)}"
            return base

    # ──────────────────────────────────────────────────────────────
    # SCAN MULTI-DIREÇÃO
    # ──────────────────────────────────────────────────────────────
    def scan(self, df: pd.DataFrame) -> Dict:
        """
        Escaneia BUY e SELL e retorna o melhor setup.
        """
        buy  = self.find_entry(df, "BUY")
        sell = self.find_entry(df, "SELL")

        if buy["valid"] and sell["valid"]:
            best = buy if buy["risk_reward"] >= sell["risk_reward"] else sell
        elif buy["valid"]:
            best = buy
        elif sell["valid"]:
            best = sell
        else:
            best = {"valid": False, "reject_reason": "Nenhum setup válido encontrado"}

        return {
            "best":      best,
            "buy_scan":  buy,
            "sell_scan": sell,
        }
