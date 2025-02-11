from naeural_client import Session


if __name__ == '__main__':
  sess = Session(
    silent=False,
    debug=True,
  )
  print(sess.get_client_address())
  
  sess.wait(seconds=15, close_session=True)