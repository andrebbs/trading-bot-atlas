import unittest
import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "core" / "novadexy_executor.py"
_spec = importlib.util.spec_from_file_location("novadexy_executor", _MODULE_PATH)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
NovaDexyExecutor = _module.NovaDexyExecutor
NovaDexySettings = _module.NovaDexySettings

direction_to_code = _module.direction_to_code
normalize_symbol = _module.normalize_symbol
class F:
 def __init__(self):self.calls=[]
 def post(self,*a,**k):self.calls.append((a,k));return type("R",(),{"raise_for_status":lambda s:None,"json":lambda s:{"status":"success","transaction_id":"1"}})()
class T(unittest.TestCase):
 def test_map(self):self.assertEqual(direction_to_code("COMPRA"),1);self.assertEqual(direction_to_code("SELL"),0);self.assertEqual(normalize_symbol("BTC/USDT"),"BTCUSDT")
 def test_dry(self):
  f=F();r=NovaDexyExecutor(NovaDexySettings(False,"dry_run","x","",114,500,1,1),f).place_order("BTC/USDT","BUY",1);self.assertTrue(r["ok"]);self.assertFalse(f.calls)
 def test_demo(self):
  f=F();r=NovaDexyExecutor(NovaDexySettings(True,"demo","x","t",114,500,1,1),f).place_order("BTC/USDT","SELL",1);self.assertTrue(r["executed"]);self.assertEqual(f.calls[0][1]["json"]["direction"],0)
if __name__=="__main__":unittest.main()
