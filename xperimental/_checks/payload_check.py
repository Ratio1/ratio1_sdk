import json

from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine



if __name__ == '__main__' :  
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng = DefaultBlockEngine(
    log=l, name="bleo", 
    config={
        "PEM_FILE"     : "bleo.pem",
        "PASSWORD"     : None,      
        "PEM_LOCATION" : "data"
      }
  )
  
  data = {'EE_DEST': [
'0xai_At8N0Qgz78sBLgPtMgifmCabJGkgEzgkEP-1laDggXVM','0xai_AleLPKqUHV-iPc-76-rUvDkRWW4dFMIGKW1xFVcy65nH',
'0xai_A-Bn9grkqH1GUMTZUqHNzpX5DA6PqducH9_JKAlBx6YL','0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6'
],'EE_ENCRYPTED_DATA': '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',
'EE_ETH_SENDER': '0x93B04EF1152D81A0847C2272860a8a5C70280E14','EE_ETH_SIGN': '0xBEEF',
'EE_EVENT_TYPE': 'PAYLOAD','EE_HASH': 'd58f608dc5eed76c4e88a9b9e0ff330dd2a42aef8154c31ad6f6c2af01f7d899',
'EE_IS_ENCRYPTED': True,'EE_MESSAGE_ID': '87d8ee21-381a-4f45-8177-848d04cd2d62',
'EE_PAYLOAD_PATH': ['nen-aid02','admin_pipeline',
'CHAIN_STORE_BASE','CHAIN_STORE_BASE_INST'],
'EE_SENDER': '0xai_A-Bn9grkqH1GUMTZUqHNzpX5DA6PqducH9_JKAlBx6YL','EE_SIGN': 'MEYCIQDMuget44QOm-djORhfYO8vOKjHEhVPIhTIvdyhObECogIhAL_mpC9pfu5dGz_h1OiKTPUpWNMrcItgcaR8ikDbEXbL',
'EE_TIMESTAMP': '2025-01-24 14:39:22.555466','EE_TIMEZONE': 'UTC+2',
'EE_TZ': 'Europe/Bucharest','EE_VERSION': '2.5.43',
'INITIATOR_ADDR': None,'INITIATOR_ID': None,
'MODIFIED_BY_ADDR': None,'MODIFIED_BY_ID': None,
'SB_IMPLEMENTATION': None,'SESSION_ID': None
}

  

  res = eng.verify(data)
  l.P(f"Result: {json.dumps(res, indent=2)}", color='b')
  
  if data['EE_IS_ENCRYPTED']:
    l.P("Data is encrypted", color='y')
    if eng.contains_current_address(data['EE_DEST']):
      enc_data = data['EE_ENCRYPTED_DATA']
      dec_data = eng.decrypt(encrypted_data_b64=enc_data, sender_address=data['EE_SENDER'])
      data = {
        **data,
        **json.loads(dec_data)
      }
      l.P(f"Decrypted data: {json.dumps(data, indent=2)}", color='g')
    else:
      l.P("Data is not for this address", color='r')