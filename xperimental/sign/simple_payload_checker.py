from ratio1 import Logger
from ratio1.bc import DefaultBlockEngine


if __name__ == '__main__':
  l = Logger("ENC", base_folder=".", app_folder="_local_cache", silent=True)
  eng = DefaultBlockEngine(name='test', log=l)
  
  data = {
    "auth": {
          "error": "Invalid signature: Corrupted digest!"
        },
    "server_alias": "nen-2",
    "server_version": "2.6.44",
    "server_time": "2025-01-30 19:55:00",
    "server_current_epoch": 47,
    "server_uptime": "2:31:38",
    "EE_SIGN": "MEYCIQDA1vnKWMWw8tPlniB9k_EUk_F5z1tyYkWjA_dJn1pE2AIhAPok-4fPt3AbEF8GXGRYNT4tY9_IWz_PTrJ3OVnq_hc-",
    "EE_SENDER": "0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6",
    "EE_ETH_SENDER": "0x129a21A78EBBA79aE78B8f11d5B57102950c1Fc0",
    "EE_ETH_SIGN": "0xBEEF",
    "EE_HASH": "90af17fe82db3a4e9ff6192f71414fb3de3ca26b7aaef4c8b2c086958efbe2d4"
  }

  
  res = eng.verify(data)
  l.P(f"My address is:\n  Int: {eng.address}\n  ETH: {eng.eth_address}", show=True)
  l.P(f"res: {res}", show=True, color='g' if res.valid else 'r')