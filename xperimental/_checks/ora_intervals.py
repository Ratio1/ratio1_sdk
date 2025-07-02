from ratio1 import Session



if __name__ == "__main__":
  sess = Session(
    silent=False,
    verbosity=3,
  )
  
  sess.P("Starting session to check oracle intervals", verbosity=2, color='g')
  sess.wait(seconds=50, close_session=True)
  
  sess._netmon_check_oracles_cadence()
  