"""
Position Sizing — ATLAS v2
src/core/position_sizing.py
"""
import math

class PositionSizing:
    def __init__(self, risk_per_trade=0.01):
        """risk_per_trade = % da conta por trade (ex: 0.01 = 1%)"""
        self.risk_per_trade = risk_per_trade

    def calculate_position(self, balance, entry, stop_loss):
        risk_amount = balance * self.risk_per_trade
        stop_distance = abs(entry - stop_loss)

        if stop_distance == 0:
            return 0

        return risk_amount / stop_distance

    def calculate_trade(self, balance, entry, stop_loss, take_profit):
        size = self.calculate_position(balance, entry, stop_loss)

        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)

        rr = reward / risk if risk > 0 else 0

        return {
            "position_size": size,
            "risk_amount": balance * self.risk_per_trade,
            "risk_reward": rr
        }
