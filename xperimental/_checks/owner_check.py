import pandas as pd
from ratio1 import Session


if __name__ == '__main__':
  sess = Session(
    silent=False,
    verbosity=3,
  )
  
  addr = '0xai_A-TEw0kO3USyFBjyCaHP99trg3CmwIBuEZw37YyBJytK'
  df = sess.get_nodes_apps(owner=addr, as_df=True)
  
  sess.P(f"Results:\n{df}", color='b')
    
  sess.wait(seconds=15, close_session=True)