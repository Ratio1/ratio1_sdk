import json

from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine



if __name__ == '__main__' :
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  
  
  data = {
  "EE_IS_ENCRYPTED": True,
  "EE_ENCRYPTED_DATA": "fwcctxETcji64z/KAYFmyWE8RDrJwm2BToMMZD9uesGtWatmDA1nadqpaAwlQajJg9SYb6jeadwxeIqg15VlDmNO9X2dxSiu151Dos900kx2Y8dM3q/S7A==",
  "EE_ID": "0xai_A9gulGoLPxo7hOo05GIeSvfld_IF_CucTnP00CznjmJN",
  "SESSION_ID": "SolisClient_bf2d",
  "INITIATOR_ID": "SolisClient_bf2d",
  "EE_SENDER": "0xai_Ag28FO6Yg254w-RHsBtODc_WLq7jz4SwfUAW7S7zP0U1",
  "TIME": "2025-01-07 00:37:16.291005",
  "EE_SIGN": "MEQCIH9T4_zB4v8cgjhUAwOvELrthGCUZ4v87LR-5DnFetkuAiAm2nOoZIitma10skQbuf12Yp9l_M7zyAcG9mWScuPZGw==",
  "EE_HASH": "7d7d49f39d1f870af74bece27262d9b050b5358a15c71b249150d04a712ce72c"
  }
  
  
  eng1 = DefaultBlockEngine(
    log=l, name="test1", 
    config={
        "PEM_FILE"     : "stg-0.pem",
        "PASSWORD"     : None,      
        "PEM_LOCATION" : "data"
      }
  )
  
  
  ver = eng1.verify(data)
  
  eng1.P(f"Signature: {'OK' if ver.valid else 'ERROR'}, {ver}", color='g' if ver.valid else 'r')
  
  decr = eng1.decrypt(
    encrypted_data_b64=data["EE_ENCRYPTED_DATA"],
    sender_address=data["EE_SENDER"],
    debug=True,
  )
  eng1.P(f"Decrypted: {decr}")
