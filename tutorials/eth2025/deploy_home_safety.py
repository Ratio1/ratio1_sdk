from ratio1 import Instance, Payload, Pipeline, Session


if __name__ == '__main__':

  session: Session = Session()

  # Please, fill in below your node's address
  # this code assumes the node have "allowed" the SDK to deploy the pipeline
  node_address = ''


  session.wait_for_node(node_address)  # we wait for the node to be ready
  pipeline: Pipeline = session.create_pipeline(
    node=node_address,
    name='home_camera_security_pipeline',
    data_source="video_stream_cv2",
    # Fill in below the rtsp URL for your camera and define cap_resolution to camera's FPS + 1
    url='',
    cap_resolution=16,
  )

  instance: Instance = pipeline.create_plugin_instance(
    signature='HOME_SAFETY',
    instance_id='inst01',
    debuggin_mode=True,
  )

  pipeline.deploy()

  session.wait(
    # seconds=99999999,  # we wait the session for 60 seconds
    close_pipelines=False,  # we close the pipelines after the session
    close_session=False,  # we close the session after the session
    wait_close=False
  )
  session.P("Main thread exiting...")
