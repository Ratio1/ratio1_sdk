import os
import json


from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine



if __name__ == '__main__' :
  
  l = Logger("ENC")
  eng = DefaultBlockEngine(
    log=l, name="default", 
    user_config=True
  )
  
  eng.reset_network("devnet")
  
  l.P(f"Checking web3 API on {eng.evm_network}", color='b')
  
  job_id = 1
  job_details = eng.web3_get_job_details(job_id)

  l.P(f"Job Details for job id {job_id}:\n{json.dumps(job_details, indent=2)}", color='b')