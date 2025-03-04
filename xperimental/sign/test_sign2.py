import json
from copy import deepcopy


from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine


if __name__ == '__main__':
  
  faulty_stuff = {  
    0: {'something': 'wrong', 'number': 22, 'sss': [222, 'ppp']},
    4: {'something': 'wrong', 'number': 22, 'sss': [222, 'ppp']},  
    5: {'something': 'wrong', 'number': 22, 'sss': [222, 'ppp']},
    6: {'something': 'wrong', 'number': 22, 'sss': [222, 'ppp']},  
    3333: {'something': 'wrong', 'number': 22, 'sss': [222, 'ppp']},
  }
  
  dct_data = {
    "faulty_stuff": faulty_stuff,
  }
  
  
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng1 = DefaultBlockEngine(
    log=l, 
    name="default",
    config={}
  )  

  eng2 = DefaultBlockEngine(
    log=l, 
    name="default",
    config={}
  )  
  
  data1 = deepcopy(faulty_stuff)
  str_for_hash1 = eng1._generate_data_for_hash(data1, replace_nan=True)
  print(f"\n\n{str_for_hash1}\n\n")
  sign1 = eng1.sign(data1)
  msg1 = l.safe_dumps_json(data1, replace_nan=False, ensure_ascii=False)
  print(f"\n\n{msg1}\n\n")
  
  
  msg2 = msg1
  data2 = json.loads(msg2)
  str_for_hash2 = eng2._generate_data_for_hash(data2, replace_nan=True)
  print(f"\n\n{str_for_hash2}\n\n")
  result = eng2.verify(data2)
  print(f"\n\ncheck 1: {result}\n\n")
  
  
  
  
  
  
  
  