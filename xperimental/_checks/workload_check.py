import pandas as pd
from ratio1 import Session


if __name__ == '__main__':
  sess = Session(silent=True, verbosity=3)
  sess.P(sess.get_client_address(), color='g')
  
  node = '0xai_AxLOEgr3I1SCi3wp1c3tYxgVEpZrfV_qpDoG3_J8Sc4e'
  df = sess.get_nodes_apps(node=node, show_full=True, as_json=False, as_df=True)
  sess.P(f"Results:\n{df}", color='b', show=True)
    
  sess.wait(seconds=15, close_session=True)