from naeural_client import CustomPluginTemplate, Session, PLUGIN_TYPES

# this tutorial can be run only on the local edge node
# because it uses ngrok to expose the fastapi server
# and this requires a ngrok auth token

# See https://naeural-001.ngrok.app/docs


def remote_execute(plugin: CustomPluginTemplate, code: str):
  result = plugin.execute_remote_code(code=code)
  return {
    "Congratulations": "You have successfully executed the code!",
    **result,
  }


if __name__ == "__main__":
  session = Session()

  node = "0xai_At8N0Qgz78sBLgPtMgifmCabJGkgEzgkEP-1laDggXVM"
  session.wait_for_node(node)

  instance: PLUGIN_TYPES.CUSTOM_WEBAPI_01
  pipeline, instance = session.create_web_app(
    node=node,
    name="naeural_code_sandbox_copycat_app",
    signature=PLUGIN_TYPES.CUSTOM_WEBAPI_01, # not mandatory as it is the default value

    ngrok_edge_label="edghts_2jSQ4nm5TuzGgHh8I0wlfDz3Vr0",  # https://naeural-001.ngrok.app
    use_ngrok=True,
  )

  # POST request on <domain>/remote_execute (with body as json with 1 key: code)
  instance.add_new_endpoint(remote_execute, method="post")

  # add a html file to the web app, accessible at <domain>/
  instance.add_new_html_endpoint(
    html_path="tutorials/9. code_sandbox_from_scratch_assets/index.html",
    web_app_file_name="index.html",
    endpoint_route="/",
  )

  pipeline.deploy()


  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   in production, you would not need this code as the script can close after the pipeline will be sent
  session.run(
    wait=True, # wait for the user to stop the execution or a given time
    close_pipelines=True # when the user stops the execution, the remote edge-node pipelines will be closed
  )