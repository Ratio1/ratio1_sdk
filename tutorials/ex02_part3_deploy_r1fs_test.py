import json
from naeural_client import Instance, Payload, Pipeline, Session, PAYLOAD_DATA

def instance_on_data(pipeline: Pipeline, payload: Payload):
  # we extract the payload and do a minimal processing
  # this is the payload key sent by the demo plugin
  R1FS_DEMO_DATA_KEY = "R1FS_DATA" 
  # next convert to the data object for convenience
  data = payload.data 
  # then we extract the sender alias directly from the payload
  sender_alias = data[PAYLOAD_DATA.EE_ID] 
  # we extract the r1fs data if it is present
  r1fs_data = data.get(R1FS_DEMO_DATA_KEY) 
  if r1fs_data is None:
    # we ignore the payload if the data is not present
    return 
  # then we extract the R1FS file originator (creator) from the demo data
  read_file_originator = r1fs_data["owner_id"] 
  # we print the data 
  pipeline.P("Data received from worker '{}' from file created by '{}':\n {}".format(
    sender_alias, read_file_originator, json.dumps(r1fs_data, indent=2)
  ))
  return

if __name__ == '__main__':

  session: Session = Session()
  
  # this code assumes the node have "allowed" the SDK to deploy the pipeline
  nodes = [
    '0xai_A2LfyeItL5oEp7nHONlczGgwS3SV8Ims9ujJ0soJ6Anx',
    '0xai_AqgKnJMNvUvq5n1wIin_GD2i1FbZ4FBTUJaCI6cWf7i4',
  ]

  for node in nodes:
    session.P(f"Deploying pipeline to node: {node}")
    session.wait_for_node(node) # we wait for the node to be ready
    pipeline: Pipeline = session.create_pipeline(
      node=node, name='r1fs_demo_pipeline', data_source='Void',
      debug=True,
    )
    # The ideea is that we create a plugin instance that listens for data
    # on ChainStorage from other plugins/nodes that create R1FS demo files
    # while itself also creating R1FS demo files
    instance: Instance = pipeline.create_plugin_instance(
      signature='R1FS_DEMO', on_data=instance_on_data,
      instance_id='inst01',
      debug=True,
    )

    pipeline.deploy()
  WAIT_TIME = 150
  session.P(f"All pipelines deployed, we wait for {WAIT_TIME} seconds...")
  session.wait(
    seconds=WAIT_TIME,            # we wait the session for 60 seconds
    close_pipelines=True,   # we close the pipelines after the session
    close_session=True,     # we close the session after the session
  )
  session.P("Main thread exiting...")
