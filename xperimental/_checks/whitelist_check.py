"""
Whitelist checker

"""
import os 
import json

from ratio1 import Session


if __name__ == '__main__':
  
  NODE = "0xai_AqZ0hh2Y9a_2N8nwHbexlt1YFGLyfptv28WnELNa1EaD"  
  
  sess = Session(
    silent=False,
    # verbosity=3,
  )
  log = sess.log
  
  # now wait for node and display the whitelist
  sess.wait_for_node(NODE)
      
  sess.wait(seconds=10, close_session=True)

  # get the whitelist
  wl = sess.get_node_whitelist(NODE)
  
  log.P(f"Whitelist for {NODE}:\n {json.dumps(wl, indent=2)}", color='g')
  