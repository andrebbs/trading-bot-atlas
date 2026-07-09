#!/usr/bin/env python3
"""
ATLAS - signal_guard.py
Camada de proteção/observabilidade plugável no telegram_bot, sem reescrever o bot.

Fornece:
  - ADXGate:        ADX afrouxado 15/18 -> 12/15 (tunável via env)
  - SignalThrottle: trava de N sinais/hora por ativo (anti-spam)
  - Heartbeat:      "signal-or-explain" -> se nada disparar, reporta o
                    MELHOR candidato bloqueado e o motivo.

Integração (no telegram_bot.py):
    from signal_guard import ADXGate, SignalThrottle, Heartbeat

    adx_gate   = ADXGate()
    throttle   = SignalThrottle()
    heartbeat  = Heartbeat(send_fn=self.send_telegram_message)

    # no loop, para cada candidato avaliado:
    heartbeat.observe(symbol, direction, final_score_pct, confluence, block_reason)

    if not adx_gate.ok(adx_value):
        heartbeat.observe(symbol, direction, final_score_pct, confluence, "ADX baixo")
        continue
    if not throttle.allow(symbol):
        continue
    # ... dispara sinal ...
    throttle.register(symbol)

    # 1x por ciclo (ex: fim do scan de todos os ativos):
    heartbeat.tick()
"""
import os, time, threading


class ADXGate:
    """ADX afrouxado. Default 12 (entrada) / 15 (forte). Antes: 15/18."""
    def __init__(self, min_adx=None, strong_adx=None):
        self.min_adx = float(os.getenv('ATLAS_ADX_MIN', min_adx if min_adx is not None else 12.0))
        self.strong_adx = float(os.getenv('ATLAS_ADX_STRONG', strong_adx if strong_adx is not None else 15.0))

    def ok(self, adx_value):
        try:
            return float(adx_value) >= self.min_adx
        except (TypeError, ValueError):
            return False

    def is_strong(self, adx_value):
        try:
            return float(adx_value) >= self.strong_adx
        except (TypeError, ValueError):
            return False


class SignalThrottle:
    """Máximo de N sinais/hora POR ativo. Thread-safe. Janela deslizante."""
    def __init__(self, max_per_hour=None, window_sec=3600):
        self.max_per_hour = int(os.getenv('ATLAS_MAX_SIGNALS_PER_HOUR',
                                          max_per_hour if max_per_hour is not None else 2))
        self.window = int(window_sec)
        self._hist = {}            # symbol -> [timestamps]
        self._lock = threading.Lock()

    def _prune(self, symbol, now):
        cutoff = now - self.window
        self._hist[symbol] = [t for t in self._hist.get(symbol, []) if t >= cutoff]

    def allow(self, symbol):
        now = time.time()
        with self._lock:
            self._prune(symbol, now)
            return len(self._hist.get(symbol, [])) < self.max_per_hour

    def register(self, symbol):
        now = time.time()
        with self._lock:
            self._prune(symbol, now)
            self._hist.setdefault(symbol, []).append(now)

    def remaining(self, symbol):
        now = time.time()
        with self._lock:
            self._prune(symbol, now)
            return max(0, self.max_per_hour - len(self._hist.get(symbol, [])))


class Heartbeat:
    """
    'Signal-or-explain': se num ciclo nenhum sinal disparar, manda 1 mensagem
    com o MELHOR candidato bloqueado e o motivo — para você nunca ficar no escuro.
    Só envia heartbeat a cada `interval_sec` (evita flood). Tunável via env.
    """
    def __init__(self, send_fn=None, interval_sec=None):
        self.send_fn = send_fn
        self.interval = int(os.getenv('ATLAS_HEARTBEAT_SEC',
                                      interval_sec if interval_sec is not None else 1800))
        self.enabled = os.getenv('ATLAS_HEARTBEAT', '1') == '1'
        self._best = None          # (score, symbol, direction, conf, reason)
        self._signal_fired = False
        self._last_sent = 0.0
        self._lock = threading.Lock()

    def observe(self, symbol, direction, score_pct, confluence, reason=None):
        with self._lock:
            cand = (int(score_pct or 0), symbol, direction, int(confluence or 0), reason or "—")
            if self._best is None or cand[0] > self._best[0]:
                self._best = cand

    def mark_signal_fired(self):
        with self._lock:
            self._signal_fired = True

    def tick(self):
        """Chame 1x ao fim de cada ciclo de scan."""
        now = time.time()
        with self._lock:
            fired = self._signal_fired
            best = self._best
            due = (now - self._last_sent) >= self.interval
            # reset do ciclo
            self._signal_fired = False
            self._best = None
            if fired or not self.enabled or not due:
                return None
            self._last_sent = now

        if best is None:
            msg = "💓 ATLAS ativo | nenhum candidato avaliado neste ciclo."
        else:
            score, sym, direction, conf, reason = best
            msg = (f"💓 ATLAS ativo | 0 sinais neste ciclo.\n"
                   f"Melhor candidato bloqueado: {sym} {direction} "
                   f"({score}%, {conf}/5)\nMotivo: {reason}")
        if self.send_fn:
            try:
                self.send_fn(msg)
            except Exception:
                pass
        return msg
