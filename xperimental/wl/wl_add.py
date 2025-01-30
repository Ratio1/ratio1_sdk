import json
from copy import deepcopy


from naeural_client import Logger, const
from naeural_client.bc import DefaultBlockEngine


if __name__ == '__main__':
  
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng = DefaultBlockEngine(
    log=l, 
    name="default",
  )
  l.P("Whitelist:\n{}".format("\n".join([
    a + (("  " + b) if len(b)>0 else "") for a,b in zip(*eng.whitelist_with_names)
  ])))
  
  to_add = [
    "0xai_A-Bn9grkqH1GUMTZUqHNzpX5DA6PqducH9_JKAlBx6YL         nen-aid02",
    "0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6             nen-2",
    "0xai_AwxGtRVqRlUrUoZNvf827uOswFmCkFXXguRmkpnyJBhQ",
  ]
  
  eng.add_address_to_allowed("0xai_AszI8IKn985-IdDULXPrgYS5lnwg9PDmB95VGMYyltf4 bleo_core")
  eng.add_address_to_allowed("0xai_AszI8IKn985-IdDULXPrgYS5lnwg9PDmB95VGMYyltf4")
  eng.add_address_to_allowed("0xai_AszI8IKn985-IdDULXPrgYS5lnwg9PDmB95VGMYyltf4 bleo_core")
  eng.add_address_to_allowed("0xai_adresafoartegreistatotal.................")
  eng.add_address_to_allowed(to_add)
  
  
  l.P("Whitelist:\n{}".format("\n".join([
    a + (("  " + b) if len(b)>0 else "") for a,b in zip(*eng.whitelist_with_names)
  ])))
  