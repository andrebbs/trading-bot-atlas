"""Crypto IDX candle data fetcher for the Stockity/Binomo broker.

Stockity exposes a REST endpoint (``/candles/v1/{ric}/{start}/{frame}``)
that returns raw tick candles (only 1s and 5s frames are populated; other
frame values return an empty list even though they don't error). There is
no native M1/M5 feed, so this module fetches 5s candles and aggregates
them client-side into the M1/M5 candles the ATLAS Crypto IDX rejection
strategy needs.

Important protocol quirks discovered via manual reverse engineering:
- The broker's clock is NOT wall-clock UTC (Crypto IDX is a synthetic
  index with its own internal clock, observed far in the future during
  testing). Callers must anchor requests off the ``Date`` response header
  from the API itself, never off local system time.
- ``start`` must be truncated to the top of the hour (``HH:00:00``); the
  endpoint silently returns an empty list for any other minute/second
  offset, even though the HTTP call itself succeeds with ``200``.
- Each successful hour-aligned request returns up to ~1h of 5s candles
  (accounting for the current in-progress hour returning fewer).
"""
from __future__ import annotations

import datetime
import email.utils
import logging
import uuid
from dataclasses import dataclass
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

CANDLE_FRAME_SECONDS = 5  # only frame Stockity actually populates besides 1s


@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float
    created_at: datetime.datetime


def _log(msg: str) -> None:
    logger.info("[STOCKITY-DATA] %s", msg)


class StockityMarketData:
    """Fetches and aggregates Crypto IDX candles from Stockity's REST API."""

    def __init__(self, email: str, password: str, platform: str, timeout: float = 15.0):
        if not email or not password:
            raise ValueError("Credenciais Stockity ausentes para buscar candles")
        self.platform = platform
        self.timeout = timeout
        self.device_id = uuid.uuid4().hex
        self._token: Optional[str] = None
        self._login(email, password)

    def _login(self, email: str, password: str) -> None:
        headers = {
            "cookie": f"authtoken=; device_type=web; device_id={self.device_id}",
            "device-id": self.device_id,
            "device-type": "web",
            "origin": f"https://{self.platform}",
            "referer": f"https://{self.platform}/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            ),
            "user-timezone": "UTC",
        }
        resp = requests.post(
            f"https://api.{self.platform}/passport/v2/sign_in?locale=en",
            headers=headers,
            json={"email": email, "password": password},
            timeout=self.timeout,
        ).json()
        if "data" not in resp or "authtoken" not in resp.get("data", {}):
            raise RuntimeError(f"Stockity login falhou: {resp}")
        self._token = resp["data"]["authtoken"]

    def _candle_headers(self) -> dict:
        return {
            "device-id": self.device_id,
            "device-type": "web",
            "authorization-token": self._token or "",
            "user-timezone": "UTC",
            "accept": "application/json, text/plain, */*",
        }

    def _server_now(self) -> datetime.datetime:
        """Read the broker's own clock from an HTTP response header.

        Crypto IDX runs on the broker's synthetic clock, not real-world
        UTC, so local system time cannot be used to build candle queries.
        """
        probe = requests.get(
            f"https://api.{self.platform}/candles/v1/{self._ric_encoded()}/2020-01-01T00:00:00/5?locale=br",
            headers=self._candle_headers(),
            timeout=self.timeout,
        )
        date_header = probe.headers.get("date")
        if not date_header:
            raise RuntimeError("Stockity não retornou header 'date' para sincronizar o relógio")
        return email.utils.parsedate_to_datetime(date_header)

    def _ric_encoded(self, ric: str = "Z-CRY/IDX") -> str:
        return ric.replace("/", "%2F")

    def fetch_5s_candles(self, ric: str = "Z-CRY/IDX", hours_back: int = 3) -> List[Candle]:
        """Fetch up to ``hours_back`` hours of raw 5s candles, oldest first."""
        server_now = self._server_now()
        hour_start = server_now.replace(minute=0, second=0, microsecond=0)
        all_rows: List[dict] = []
        for i in range(hours_back, -1, -1):
            start = hour_start - datetime.timedelta(hours=i)
            url = (
                f"https://api.{self.platform}/candles/v1/{self._ric_encoded(ric)}/"
                f"{start.strftime('%Y-%m-%dT%H:%M:%S')}/{CANDLE_FRAME_SECONDS}?locale=br"
            )
            resp = requests.get(url, headers=self._candle_headers(), timeout=self.timeout)
            data = resp.json().get("data", []) if resp.status_code == 200 else []
            all_rows.extend(data)
        candles = [
            Candle(
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                created_at=datetime.datetime.fromisoformat(
                    row["created_at"].replace("Z", "+00:00")
                ),
            )
            for row in all_rows
        ]
        candles.sort(key=lambda c: c.created_at)
        return candles

    @staticmethod
    def aggregate(candles: List[Candle], period_seconds: int) -> List[Candle]:
        """Aggregate raw 5s candles into larger buckets (e.g. M1=60, M5=300)."""
        if not candles:
            return []
        buckets: dict[int, List[Candle]] = {}
        epoch = candles[0].created_at
        for c in candles:
            bucket_index = int((c.created_at - epoch).total_seconds() // period_seconds)
            buckets.setdefault(bucket_index, []).append(c)
        aggregated: List[Candle] = []
        for idx in sorted(buckets):
            group = buckets[idx]
            aggregated.append(
                Candle(
                    open=group[0].open,
                    high=max(c.high for c in group),
                    low=min(c.low for c in group),
                    close=group[-1].close,
                    created_at=group[0].created_at,
                )
            )
        return aggregated

    def get_m1_m5_candles(
        self, ric: str = "Z-CRY/IDX", hours_back: int = 3
    ) -> tuple[List[Candle], List[Candle]]:
        """Convenience helper: fetch raw data and return (m1_candles, m5_candles)."""
        raw = self.fetch_5s_candles(ric=ric, hours_back=hours_back)
        m1 = self.aggregate(raw, 60)
        m5 = self.aggregate(raw, 300)
        return m1, m5
