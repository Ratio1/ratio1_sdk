from naeural_client import Session


if __name__ == '__main__':
  sess = Session(
    silent=False,
    verbosity=3,
  )
  sess.P(sess.get_client_address(), color='g')
  
  sess.wait(seconds=15, close_session=True)