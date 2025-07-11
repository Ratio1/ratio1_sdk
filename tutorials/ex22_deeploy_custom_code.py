#!/usr/bin/env python3

import json

from ratio1.logging import Logger
from ratio1.const import DEEPLOY_CT
from ratio1 import Session, CustomPluginTemplate, PLUGIN_TYPES

def plugin_custom_code(plugin: CustomPluginTemplate):
  """
  The custom code that will be executed on the main thread.

  Parameters
  ----------
  plugin : CustomPluginTemplate
      The plugin instance. It will be replaced with the plugin instance object on the remote side.

  Returns
  -------
  list
      The result of the custom code.
      In our case, the list of prime numbers found in the random numbers generated.
  """

  def is_prime(n):
    if n <= 1:
      return False
    for i in range(2, int(plugin.np.sqrt(n)) + 1):
      if n % i == 0:
        return False
    return True

  random_numbers = plugin.np.random.randint(0, 100, 10)

  are_primes = plugin.threadapi_map(is_prime, random_numbers, n_threads=2)

  prime_numbers = []
  for i in range(len(random_numbers)):
    if are_primes[i]:
      prime_numbers.append(random_numbers[i])

  return prime_numbers



if __name__ == '__main__':
  # we do not set up any node as we will not use direct SDK deployment but rather the Deeploy API
  session = Session()
  logger = Logger("DEEPLOY", base_folder=".", app_folder="deeploy_custom_code")

  private_key_path = '' # The path to your Private Key
  target_nodes = [
    "",
    ]  # replace with your target node address

  launch_result = session.deeploy_custom_code(
    name="r1_deeploy_custom_code",
    signer_private_key_path=private_key_path,
    target_nodes=target_nodes,
    # target_nodes_count=0,  # if you are specifying target nodes addresses, set this to 0
    logger=logger,
    custom_code=plugin_custom_code,
    config={
      'PROCESS_DELAY': 10
    }
  )

  session.P(json.dumps(launch_result))

  if launch_result and launch_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.STATUS) == DEEPLOY_CT.DEEPLOY_STATUS.FAIL:
    session.P("Deeploy custom code launch failed:", launch_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.ERROR, 'Unknown error'))
    exit(1)
  print("Deeploy custom code launched successfully.")

  session.sleep(60)

  # no neeed for further `sess.deploy()` as the `deeploy_*` methods handle the deployment automatically
  # now we interpret the launch_result and extract app-id, etc
  # ...

  # if all ok sleep for a while to allow app testing (say 60 seconds)

  # finally use deeploy close

  close_result = session.deeploy_close(
    app_id=launch_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT][DEEPLOY_CT.DEEPLOY_KEYS.APP_ID],
    signer_private_key_path=private_key_path,
    target_nodes=target_nodes,
    logger=logger,
  )

  session.P(json.dumps(close_result))

  if close_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT] and close_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.STATUS) == DEEPLOY_CT.DEEPLOY_STATUS.FAIL:
    session.P(f"Closing deployed deeploy custom code failed. {close_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.ERROR, 'Unknown error')}")
    exit(2)

  session.P("Demo run successfully!")

  session.close()
