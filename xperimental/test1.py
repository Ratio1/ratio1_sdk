from naeural_client import Session, CustomPluginTemplate



def run_predict(plugin: CustomPluginTemplate, inputs: list, nr_steps: int) -> list:
  preds = plugin.basic_ts_fit_predict(inputs, nr_steps)
  return preds


if __name__ == '__main__':
  
  session = Session()
  my_node = "0xai_ApM1AbzLq1VtsLIidmvzt1Nv4Cyl5Wed0fHNMoZv9u4X"
  
  app, _ = session.create_web_app(
    node=my_node,
    name="ratio1_simple_predict_webapp",
    endpoints=[
      {
        "function": run_predict,
        "method": "post",
      },        
    ]
  )
  
  url = app.deploy()
  
  print("Webapp deployed at: ", url)
  
  session.wait(
    close_pipeline_on_timeout=True,
    close_session_on_timeout=True,
    timeout=60
  )