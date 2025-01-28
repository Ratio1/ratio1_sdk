from naeural_client import Logger
from naeural_client.bc import DefaultBlockEngine


if __name__ == '__main__':
  l = Logger("ENC", base_folder=".", app_folder="_local_cache", silent=True)
  eng = DefaultBlockEngine(name='test', log=l)
  
  data = {
    "name": "test",
    "data": "hello world"
  }
  
  
  res = eng.verify(data)
  l.P(f"My address is:\n  Int: {eng.address}\n  ETH: {eng.eth_address}", show=True)
  l.P(f"res: {res}", show=True)