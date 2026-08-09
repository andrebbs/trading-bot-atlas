"""NovaDexy binary-options executor — demo-only skeleton."""
from __future__ import annotations
import asyncio, os, logging
from dataclasses import dataclass
from typing import Any, Optional
import requests
logger=logging.getLogger(__name__)
DEFAULT_BASE_URL="https://novadexybroker.com"
SYMBOL_MAP={"BTC/USDT":"BTCUSDT","ETH/USDT":"ETHUSDT","SOL/USDT":"SOLUSDT","XRP/USDT":"XRPUSDT","BNB/USDT":"BNBUSDT","ADA/USDT":"ADAUSDT","DOGE/USDT":"DOGEUSDT","LTC/USDT":"LTCUSDT","EUR/USD":"EURUSD","GBP/USD":"GBPUSD","USD/JPY":"USDJPY","XAU/USD":"GOLD","OIL/BRENT":"OIL_BRENT"}
def normalize_symbol(symbol:str)->str:
    if not isinstance(symbol,str) or not symbol.strip(): raise ValueError("symbol é obrigatório")
    raw=symbol.strip().upper().replace("-","/").replace(" ","")
    return SYMBOL_MAP.get(raw,raw.replace("/",""))
def direction_to_code(direction:str|int)->int:
    if isinstance(direction,bool): raise ValueError("direction inválida")
    if direction in (0,1): return int(direction)
    v=str(direction).strip().upper()
    if v in {"BUY","UP","COMPRA","1"}: return 1
    if v in {"SELL","DOWN","VENDA","0"}: return 0
    raise ValueError("direction deve ser BUY/SELL ou 1/0")
def _flag(name,default=False): return os.getenv(name,str(default)).lower() in {"1","true","yes","on"}
@dataclass(frozen=True)
class NovaDexySettings:
    enabled:bool; mode:str; base_url:str; token:str; account_id:Optional[int]; default_amount_cents:int; default_expiration:int; timeout_seconds:float
    @classmethod
    def from_env(cls):
        mode=os.getenv("NOVADEXY_MODE","dry_run").strip().lower()
        if mode not in {"dry_run","demo"}: raise ValueError("NOVADEXY_MODE aceita somente dry_run ou demo; live não é suportado")
        account=os.getenv("NOVADEXY_ACCOUNT_ID","").strip()
        return cls(_flag("NOVADEXY_ENABLED"),mode,os.getenv("NOVADEXY_BASE_URL",DEFAULT_BASE_URL).rstrip("/"),os.getenv("NOVADEXY_TOKEN","").strip(),int(account) if account else None,int(os.getenv("NOVADEXY_DEFAULT_AMOUNT_CENTS","500")),int(os.getenv("NOVADEXY_DEFAULT_EXPIRATION","1")),float(os.getenv("NOVADEXY_TIMEOUT_SECONDS","12")))
class NovaDexyExecutor:
    def __init__(self,settings=None,session=None): self.settings=settings or NovaDexySettings.from_env(); self.session=session or requests.Session()
    def build_order_payload(self,symbol,direction,symbol_price,amount_cents=None,expiration=None):
        amount=int(amount_cents if amount_cents is not None else self.settings.default_amount_cents); expiry=int(expiration if expiration is not None else self.settings.default_expiration)
        if amount<=0 or expiry<=0 or float(symbol_price)<=0: raise ValueError("amount, expiration e symbol_price devem ser positivos")
        if self.settings.account_id is None: raise RuntimeError("NOVADEXY_ACCOUNT_ID da demo não configurado")
        return {"__token":self.settings.token,"amount":amount,"direction":direction_to_code(direction),"expiration":expiry,"symbol":normalize_symbol(symbol),"symbol_price":float(symbol_price),"selected_account":self.settings.account_id}
    def _validate_demo(self):
        if not self.settings.enabled: raise RuntimeError("NOVADEXY_ENABLED=false; execução bloqueada")
        if self.settings.mode!="demo": raise RuntimeError("somente NOVADEXY_MODE=demo pode enviar ordem")
        if not self.settings.token or not self.settings.account_id: raise RuntimeError("token ou conta demo ausente")
    def place_order(self,symbol,direction,symbol_price,amount_cents=None,expiration=None):
        payload=self.build_order_payload(symbol,direction,symbol_price,amount_cents,expiration)
        if self.settings.mode=="dry_run": return {"ok":True,"mode":"DRY_RUN","executed":False,"payload":payload}
        self._validate_demo()
        try:
            r=self.session.post(self.settings.base_url+"/publicapi/binary/transaction",json=payload,timeout=self.settings.timeout_seconds); r.raise_for_status(); data=r.json()
            ok=str(data.get("status","")).lower()=="success"
            return {"ok":ok,"mode":"DEMO","executed":ok,"response":data,**({} if ok else {"error":str(data.get("message") or data.get("error") or "ordem recusada")})}
        except (requests.RequestException,ValueError) as exc: return {"ok":False,"mode":"DEMO","error":str(exc)}
    async def place_order_async(self,**kwargs:Any): return await asyncio.to_thread(self.place_order,**kwargs)
def get_executor(): return NovaDexyExecutor()
