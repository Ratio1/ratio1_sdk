"""
ex25_local_serving_api.py
---------------------------------

This tutorial demonstrates how to deploy and use the LOCAL_SERVING_API plugin.

The LOCAL_SERVING_API plugin:
- Creates a FastAPI server accessible only via localhost (no tunnel/ngrok)
- Does NOT require token authentication (localhost only)
- Uses IS_LOOPBACK_PLUGIN = True to route outputs back to the loopback DCT queue
- Works with Loopback data capture type pipelines
- Provides simple REST endpoints for data processing

This is ideal for:
- Internal services that don't need external access
- Testing and development
- Local data processing pipelines
- Services that need to feed data back into the edge node processing loop
"""

import os
import time
import requests
from ratio1 import Session

def test_endpoints(base_url: str, session):
  """
  Test the various endpoints of the LOCAL_SERVING_API

  Parameters
  ----------
  base_url : str
      The base URL of the API (e.g., http://localhost:5002)
  session : Session
      The ratio1 session for logging
  """

  session.P("\n" + "="*60)
  session.P("Testing LOCAL_SERVING_API Endpoints")
  session.P("="*60 + "\n")

  # Test 1: Health check
  session.P("1. Testing health endpoint...", color='b')
  try:
    response = requests.get(f"{base_url}/health")
    session.P(f"Status: {response.status_code}", color='g' if response.status_code == 200 else 'r')
    session.P(f"Response: {response.json()}", color='g')
  except Exception as e:
    session.P(f"Error: {e}", color='r')

  print()

  # Test 2: Echo endpoint
  session.P("2. Testing echo endpoint...", color='b')
  try:
    response = requests.get(f"{base_url}/echo", params={"message": "Hello from tutorial!"})
    session.P(f"Status: {response.status_code}", color='g' if response.status_code == 200 else 'r')
    session.P(f"Response: {response.json()}", color='g')
  except Exception as e:
    session.P(f"Error: {e}", color='r')

  print()

  # Test 3: Process data
  session.P("3. Testing process_data endpoint...", color='b')
  try:
    test_data = {
      "sensor_id": "sensor_001",
      "temperature": 23.5,
      "humidity": 65.2,
      "location": "warehouse_a"
    }
    response = requests.post(f"{base_url}/process_data", json={"data": test_data})
    session.P(f"Status: {response.status_code}", color='g' if response.status_code == 200 else 'r')
    session.P(f"Response: {response.json()}", color='g')
  except Exception as e:
    session.P(f"Error: {e}", color='r')

  print()

  # Test 4: Batch process
  session.P("4. Testing batch_process endpoint...", color='b')
  try:
    batch_items = [
      {"id": 1, "value": "item_1"},
      {"id": 2, "value": "item_2"},
      {"id": 3, "value": "item_3"},
    ]
    response = requests.post(f"{base_url}/batch_process", json={"items": batch_items})
    session.P(f"Status: {response.status_code}", color='g' if response.status_code == 200 else 'r')
    session.P(f"Response: {response.json()}", color='g')
  except Exception as e:
    session.P(f"Error: {e}", color='r')

  print()

  # Test 5: Get status
  session.P("5. Testing status endpoint...", color='b')
  try:
    response = requests.get(f"{base_url}/status")
    session.P(f"Status: {response.status_code}", color='g' if response.status_code == 200 else 'r')
    session.P(f"Response: {response.json()}", color='g')
  except Exception as e:
    session.P(f"Error: {e}", color='r')

  print()

  # Test 6: Get buffer
  session.P("6. Testing get_buffer endpoint...", color='b')
  try:
    response = requests.get(f"{base_url}/get_buffer", params={"limit": 5})
    session.P(f"Status: {response.status_code}", color='g' if response.status_code == 200 else 'r')
    result = response.json()
    session.P(f"Buffer size: {result['result']['buffer_size']}", color='g')
    session.P(f"Items returned: {len(result['result']['items'])}", color='g')
  except Exception as e:
    session.P(f"Error: {e}", color='r')

  print()

  # Test 7: Process image (mockup)
  session.P("7. Testing process_image endpoint...", color='b')
  try:
    # In real usage, you would encode an actual image to base64
    fake_image_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    response = requests.post(
      f"{base_url}/process_image",
      json={
        "image_data": fake_image_data,
        "metadata": {"source": "camera_01", "resolution": "1920x1080"}
      }
    )
    session.P(f"Status: {response.status_code}", color='g' if response.status_code == 200 else 'r')
    session.P(f"Response: {response.json()}", color='g')
  except Exception as e:
    session.P(f"Error: {e}", color='r')

  print()

  # Test 8: Clear buffer
  session.P("8. Testing clear_buffer endpoint...", color='b')
  try:
    response = requests.post(f"{base_url}/clear_buffer")
    session.P(f"Status: {response.status_code}", color='g' if response.status_code == 200 else 'r')
    session.P(f"Response: {response.json()}", color='g')
  except Exception as e:
    session.P(f"Error: {e}", color='r')

  session.P("\n" + "="*60)
  session.P("Endpoint Testing Complete")
  session.P("="*60 + "\n")


if __name__ == "__main__":
  # Create a session
  session = Session(silent=True)

  # Get target node from environment or use default
  node = os.environ.get("EE_TARGET_NODE", "INSERT_YOUR_NODE_ADDRESS_HERE")

  session.P(f"Waiting for node {node} to be available for deployment...", color='b')
  session.wait_for_node(node)

  session.P("Deploying LOCAL_SERVING_API plugin...", color='b')

  # Create a loopback pipeline with the LOCAL_SERVING_API plugin
  pipeline_config = {
    "NAME": "local_api_demo",
    "TYPE": "Loopback",  # Important: Use Loopback data capture type
    "LOOPBACK_QUEUE_SIZE": 32,  # Configure the loopback queue size
    "PLUGINS": [
      {
        "SIGNATURE": "LOCAL_SERVING_API",
        "INSTANCES": [
          {
            "INSTANCE_ID": "local_api_01",
            # Optional: Override default config values
            "LOG_REQUESTS": True,
            "RESPONSE_FORMAT": "WRAPPED",
          }
        ]
      }
    ]
  }

  # Deploy the pipeline
  session.P("Creating Loopback pipeline...", color='b')
  pipeline = session.create_pipeline(
    node=node,
    name=pipeline_config["NAME"],
    data_source=pipeline_config["TYPE"],  # "Loopback"
    config={
      "LOOPBACK_QUEUE_SIZE": pipeline_config.get("LOOPBACK_QUEUE_SIZE", 32)
    }
  )

  # Add the LOCAL_SERVING_API plugin
  session.P("Adding LOCAL_SERVING_API plugin...", color='b')
  instance = pipeline.create_plugin_instance(
    signature='LOCAL_SERVING_API',
    instance_id='local_api_01',
    log_requests=True,
    response_format='WRAPPED',
  )

  # Deploy the pipeline
  session.P("Deploying pipeline...", color='b')
  pipeline.deploy()

  # Wait for the pipeline to be fully deployed
  session.P("Waiting for pipeline to be fully deployed...", color='b')
  time.sleep(5)

  # Get the local URL (since tunnel is disabled, it will be localhost)
  # Port is configured in plugin as 5082
  base_url = "http://localhost:5082"

  session.P(f"\nLOCAL_SERVING_API deployed successfully!", color='g', boxed=True)
  session.P(f"API accessible at: {base_url}", color='g')
  session.P(f"Loopback mode: ENABLED", color='g')
  session.P(f"Token authentication: DISABLED (localhost only)", color='g')

  # Note about the loopback mechanism
  session.P("\nNote: This plugin uses IS_LOOPBACK_PLUGIN = True", color='y')
  session.P("This means all payloads are routed back to the loopback DCT queue", color='y')
  session.P("instead of being emitted as downstream payloads.", color='y')
  session.P(f"Loopback queue key: loopback_dct_{pipeline_config['NAME']}\n", color='y')

  # Wait a bit more to ensure the server is ready
  session.P("Waiting for server to be ready...", color='b')
  time.sleep(3)

  # Test the endpoints
  try:
    test_endpoints(base_url, session)
  except Exception as e:
    session.P(f"Error during endpoint testing: {e}", color='r')
    session.P("Make sure the server is running and accessible on localhost", color='r')

  # Additional usage examples
  session.P("\n" + "="*60)
  session.P("Usage Examples")
  session.P("="*60 + "\n")

  session.P("You can interact with this API using:", color='b')
  session.P("1. curl commands:", color='g')
  session.P(f"   curl {base_url}/health", color='w')
  session.P(f"   curl -X POST {base_url}/process_data -H 'Content-Type: application/json' -d '{{\"data\": {{\"test\": \"value\"}}}}'", color='w')

  session.P("\n2. Python requests library:", color='g')
  session.P("   import requests", color='w')
  session.P(f"   response = requests.get('{base_url}/health')", color='w')
  session.P("   print(response.json())", color='w')

  session.P("\n3. Any HTTP client (Postman, Insomnia, etc.)", color='g')

  session.P("\n4. Browser (for GET endpoints):", color='g')
  session.P(f"   {base_url}/health", color='w')
  session.P(f"   {base_url}/status", color='w')
  session.P(f"   {base_url}/echo?message=test", color='w')

  # Keep the session running
  session.P("\nPress Ctrl+C to stop and cleanup...", color='y')

  try:
    session.run(
      wait=True,  # Wait for user to stop the execution
      close_pipelines=True  # When stopped, close the remote pipelines
    )
  except KeyboardInterrupt:
    session.P("\nStopping and cleaning up...", color='y')

  session.P("Tutorial completed!", color='g', boxed=True)
