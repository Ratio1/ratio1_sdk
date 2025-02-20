import json
from naeural_client import Instance, Payload, Pipeline, Session

def instance_on_data(pipeline: Pipeline, data: Payload):
  data = data.data
  print(f"Data received: {json.dumps(data, indent=2)}")
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
      node=node,
      name='r1fs_demo_pipeline',
      data_source='Void',
    )

    instance: Instance = pipeline.create_plugin_instance(
      signature='R1FS_DEMO',
      on_data=instance_on_data,
      instance_id='inst01',
    )

    pipeline.deploy()

  session.wait(
    seconds=300,            # we wait the session for 60 seconds
    close_pipelines=True,   # we close the pipelines after the session
    close_session=True,     # we close the session after the session
  )
  session.P("Main thread exiting...")
