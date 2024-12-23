"""

This demo starts a generic webapp and generates a dynamic URL that can be used to access the webapp.
For this demo, we will use a custom webapp that resides at a public repository.

"""

from naeural_client import CustomPluginTemplate, Session, PLUGIN_TYPES


if __name__ == "__main__":
  session = Session()

  node = "INSERT_YOUR_NODE_ADDRESS_HERE"
  session.wait_for_node(node)

  instance: PLUGIN_TYPES.CUSTOM_WEB_APP_01
  pipeline, instance = session.create_web_app(
  
  )


  url = pipeline.deploy()
  
  print(f"Webapp is now available at: {url}")

