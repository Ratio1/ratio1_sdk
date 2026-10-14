#!/usr/bin/env python3

import json
import os
import time

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
  # Configure these once before submission; retain the same IDs after timeout/restart.
  job_id = int(os.environ['DEEPLOY_JOB_ID'])
  create_request_id = os.environ['DEEPLOY_CREATE_REQUEST_ID']
  delete_request_id = os.environ['DEEPLOY_DELETE_REQUEST_ID']
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
    request_id=create_request_id,
    job_id=job_id,
    custom_code=plugin_custom_code,
    config={
      'PROCESS_DELAY': 10
    }
  )

  session.P(json.dumps(launch_result))
  accepted = launch_result['result']
  print('Deployment accepted; waiting for node readiness and any required recovery.')
  api_url, auth = session.deeploy_get_read_auth(logger, private_key_path)
  while True:
    progress = session.deeploy_get_deployment_status(
      api_url, auth, operation_id=accepted['operation_id'],
    )['result']
    if progress.get('phase') == 'completed':
      settlement = progress.get('settlement', {}).get('status')
      if progress['outcome'] != 'succeeded' or settlement in ('confirmed', 'failed'):
        break
    time.sleep(progress.get('poll_after_ms', 2000) / 1000)
  if progress['outcome'] != 'succeeded' or progress.get('settlement', {}).get('status') != 'confirmed':
    raise RuntimeError('Deployment failed; inspect the operation recovery details.')
  print('Deployment ready. Keeping it running for 60 seconds before whole-job deletion.')
  session.sleep(60)
  close_result = session.deeploy_close(
    app_id=accepted['app_id'], job_id=job_id,
    request_id=delete_request_id, expected_revision=accepted['revision'],
    signer_private_key_path=private_key_path, logger=logger,
  )
  session.P(json.dumps(close_result))
  while True:
    progress = session.deeploy_get_deployment_status(
      api_url, auth, operation_id=close_result['result']['operation_id'],
    )['result']
    if progress.get('phase') == 'completed':
      break
    time.sleep(progress.get('poll_after_ms', 2000) / 1000)
  if progress['outcome'] != 'succeeded':
    raise RuntimeError('Deletion did not complete successfully; inspect operation details.')
  print('Whole-job deletion confirmed.')
  session.close()
