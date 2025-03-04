from ratio1 import Session


if __name__ == '__main__':
  sess = Session(
    silent=False,
    verbosity=3,
  )
  
  sess.wait(seconds=15, close_session=True)