from naeural_client import Session


if __name__ == '__main__':
  sess = Session(
    silent=False
  )
  print(sess.get_client_address())