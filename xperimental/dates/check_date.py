from ratio1 import Logger

if __name__ == "__main__":
  l = Logger("DT")
  
  UTC_DATE = "2025-02-01 12:00:00"
  converted = l.utc_to_local(
    remote_datetime=UTC_DATE, 
    remote_utc=None, 
    as_string=False
  )
  l.P(f"UTC {UTC_DATE} to local {converted}")