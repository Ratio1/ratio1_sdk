from ratio1 import Logger

if __name__ == "__main__":
  logger = Logger("Test-logger")
  logger.P(logger.get_total_disk())
