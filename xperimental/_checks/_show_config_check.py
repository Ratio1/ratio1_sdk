from ratio1.utils.config import show_config

from collections import namedtuple

if __name__ == '__main__' :
  Args = namedtuple('Args', ['verbose', 'reset', 'address', 'alias', 'network'])
  args = Args(
    verbose=True,
    reset=False,
    address=False,
    alias=False,
    network=False
  )
  show_config(args)