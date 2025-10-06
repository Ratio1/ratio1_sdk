from ratio1 import Logger
from ratio1.bc import DefaultBlockEngine


if __name__ == '__main__':
  logger = Logger("ENC")
  engine = DefaultBlockEngine(
    log=logger,
    name="default",
    user_config=True,
  )

  engine.reset_network("devnet")

  network = engine.evm_network
  logger.P(f"Checking first closable job on {network}", color='b')

  try:
    job_id = engine.web3_get_first_closable_job_id()
    logger.P(f"First closable job ID: {job_id}", color='g')
  except Exception as exc:
    logger.P(f"Failed to retrieve first closable job ID: {exc}", color='r')
