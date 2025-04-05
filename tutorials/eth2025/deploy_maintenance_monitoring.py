from ratio1 import Instance, Payload, Pipeline, Session


if __name__ == '__main__':

  session: Session = Session()

  # this code assumes the node have "allowed" the SDK to deploy the pipeline
  node_address = '0xai_A7NhKLfFaJd9pOE_YsyePcMmFfxmMBpvMA4mhuK7Si1w'


  session.wait_for_node(node_address)  # we wait for the node to be ready
  pipeline: Pipeline = session.create_pipeline(
    node=node_address,
    name='maintenance_monitoring_pipeline',
    data_source="SensiboMaintenanceSensor",
    config={
      'CAP_RESOLUTION': 0.03,
      'API_KEY': '',
      'POD_UID': '',
      "SENSIBO_DEVICE_NAME": "",
      'LIVE_FEED': True
    },
  )

  instance: Instance = pipeline.create_plugin_instance(
    signature='MAINTENANCE_MONITORING',
    instance_id='maintenance_inst01',
    config={
      'ANOMALY_PROBABILITY_THRESHOLD': 0.1
    }
  )

  pipeline.deploy()

  session.wait(
    # seconds=99999999,  # we wait the session for 60 seconds
    close_pipelines=False,  # we close the pipelines after the session
    close_session=False,  # we close the session after the session
    wait_close=False
  )
  session.P("Main thread exiting...")
