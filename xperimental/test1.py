from naeural_client import Session, CustomPluginTemplate, PLUGIN_TYPES

def run_predict(plugin: CustomPluginTemplate, inputs: list[int], nr_steps: int) -> list:
  """
  Here we use the Ratio1 build in basic ML internal API
  """
  preds = plugin.basic_ts_fit_predict(inputs, nr_steps)
  # now we apply some simple heuristic to get the lower and upper bounds
  lower_bound = []
  upper_bound = []
  heuristic_factor = 0.1
  for pred in preds:
    lower_bound.append(int(pred - abs(pred * heuristic_factor)))
    upper_bound.append(int(pred + abs(pred * heuristic_factor)))
  #endfor
  result = {
    "predictions": [round(x,1) for x in preds],
    "lower_bound": lower_bound,
    "upper_bound": upper_bound
  }
  return result


if __name__ == '__main__':
  
  session = Session(silent=True)
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
  try:
    url = app.deploy()
    print("Webapp deployed at: ", url)
  except Exception as e:
    print("Error deploying webapp: ", e)
  
  session.wait(
    close_pipeline_on_timeout=True,
    close_session_on_timeout=True,
    seconds=300
  )