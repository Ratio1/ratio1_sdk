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
  logger.P(f"Checking all active jobs on {network}", color='b')

  try:
    jobs = engine.web3_get_all_active_jobs()
    logger.P(f"Found {len(jobs)} active jobs", color='g')
    if jobs:
      first_job = jobs[0]
      logger.P(f"First job snapshot: {first_job}", color='b')
  except Exception as exc:
    logger.P(f"Failed to retrieve active jobs: {exc}", color='r')
