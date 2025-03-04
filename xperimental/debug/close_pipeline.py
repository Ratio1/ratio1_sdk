from ratio1 import Session


if __name__ == '__main__':
  """
  This script will close all the pipelines from pipeline_names on all the nodes from nodes
  in case the pipelines exist and the client user is allowed on the nodes, where:
  - nodes is a list of string and/or tuple pairs:
    - string: the address of the node
    - tuple: the address of the node and an alias for the node
  - pipeline_names is a list of strings representing the names of the pipelines to be closed.

  For example:
  - nodes = ['address1', ('address2', 'alias2)]
  - pipeline_names = ['pipeline1', 'pipeline2']
  
  Assuming the following:
    - the client user is allowed only on the node with address2
    - the node on address1 has pipelines named 'pipeline1' and 'pipeline2'
    - the node on address2 only has a pipeline named 'pipeline1'
  
  The 2 pipelines on node with address1 will remain intact,
  while the 'pipeline1' on node with address2 will be closed.
  
  NOTE: If a node you you are trying to reach is unknown, it may be on a different network.
  You can try changing the network with:
  ```
  r1ctl config network --set <network_name>
  ```
  """

  session = Session(silent=True)
  nodes = [
    ('0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6', 'tr1s-02')
  ]

  pipeline_names = [
    'gigi_pipeline_01',
    'telegram_bot_blackjack'
  ]

  for node in nodes:
    node_addr, node_alias = node if isinstance(node, tuple) else (node, None)
    session.wait_for_node(node_addr)
    for pipeline_name in pipeline_names:
      try:
        current_pipeline = session.attach_to_pipeline(
          node=node_addr, name=pipeline_name
        )
        session.P(f'Pipeline {pipeline_name} on node {node_addr} was successfully attached. Closing...', show=True)
        current_pipeline.close()
      except Exception as exc:
        session.P(f"Error attaching to pipeline {pipeline_name} on node {node_addr}: {exc}", show=True)
        continue
      # endtry
    # endfor pipelines
  # endfor nodes
