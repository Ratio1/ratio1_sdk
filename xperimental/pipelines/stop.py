import os
from ratio1 import Session


if __name__ == "__main__":
  session = Session()
  
  my_node = os.getenv("EE_TARGET_NODE", "0xai_my_own_node_address") 
  my_pipeline = "telegram_bot_echo"
  
  session.close_pipeline(my_node, my_pipeline)
  session.close()