
import json


from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine



if __name__ == '__main__' :
  l = Logger("ENC", base_folder='.', app_folder='_local_cache')
  eng = DefaultBlockEngine(
    log=l, name="default", 
    config={
        # "PEM_FILE": "aid01.pem",
      }
  )
  
  REQUEST = {
    "app_name" : "SOME_APP_NAME", 
    "plugin_signature" : "SOME_PLUGIN_01",
    "target_nodes" : [
      "0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6",
      "0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-7",
    ],
    "app_params" : {
      "image" : "repo/image:tag",
      "registry" : "docker.io",
      "username" : "user",
      "password" : "password",
      "port" : 5000,
      "ENV" : {
        "ENV1" : "value1",
        "ENV2" : "value2",
      }
    }
    
  }
  