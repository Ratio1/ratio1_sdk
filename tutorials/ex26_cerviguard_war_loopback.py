"""
ex26_cerviguard_war_loopback.py
---------------------------------

CerviGuard WAR - Loopback Pipeline Testing

This tutorial demonstrates the complete CerviGuard WAR (Web Application Resource)
architecture using the loopback mechanism to test image processing pipelines.

Architecture:
  1. LOCAL_SERVING_API (FastAPI backend, IS_LOOPBACK_PLUGIN=True)
     - Receives images from UI via REST endpoints
     - Writes requests to loopback queue
     - Reads from loopback queue in process() loop
     - Calls CERVIGUARD_IMAGE_ANALYZER serving plugin directly
     - Caches results for polling

  2. Loopback DCT (Data Capture Thread)
     - Reads from shared memory queue
     - Feeds data back into pipeline

  3. CERVIGUARD_IMAGE_ANALYZER (Serving Plugin - runs in isolated process)
     - Decodes base64 images
     - Extracts dimensions and quality metrics
     - Mockup for future AI model integration

  4. CerviGuard UI (worker_app_runner - to be added by you)
     - Frontend that interacts with the API

Flow:
  UI → POST /cerviguard_submit_image → Write to loopback queue
  → Loopback DCT feeds back → process() reads from loopback
  → Calls serving plugin via dataapi_inferences()
  → Caches result → UI polls via GET /cerviguard_get_result

This setup allows you to verify the loopback mechanism works correctly
before integrating the actual AI model for cervical cancer detection.
"""
import json
import time
import requests
import base64
from ratio1 import Session
import numpy as np
from PIL import Image
import io

def encode_image_to_base64(image_path: str) -> str:
  """
  Encode an image file to base64 string

  Parameters
  ----------
  image_path : str
      Path to the image file

  Returns
  -------
  str
      Base64 encoded image string
  """
  with open(image_path, 'rb') as f:
    img_bytes = f.read()
    b64_string = base64.b64encode(img_bytes).decode('utf-8')
    return b64_string


def test_cerviguard_api(base_url: str, session):
  """
  Test the CerviGuard API endpoints

  Parameters
  ----------
  base_url : str
      Base URL of the API (e.g., http://localhost:5002)
  session : Session
      The ratio1 session for logging
  """

  session.P("\n" + "="*70)
  session.P("Testing CerviGuard WAR Loopback Pipeline")
  session.P("="*70 + "\n")

  # Test 1: Check system status
  session.P("1. Checking CerviGuard system status...", color='b')
  try:
    response = requests.get(f"{base_url}/cerviguard_status")
    session.P(f"Status: {response.status_code}", color='g' if response.status_code == 200 else 'r')
    result = response.json()
    session.P(f"Service: {result['result']['service']}", color='g')
    session.P(f"Version: {result['result']['version']}", color='g')
    session.P(f"Status: {result['result']['status']}", color='g')
  except Exception as e:
    session.P(f"Error: {e}", color='r')
    session.P("Make sure the pipeline is deployed and API is running!", color='r')
    return

  print()

  # Test 2: Create a test image (1x1 pixel red image)
  session.P("2. Creating test cervical image (mockup)...", color='b')

  # Create a small test image (100x100 red square)
  test_img = np.zeros((100, 100, 3), dtype=np.uint8)
  test_img[:, :, 0] = 255  # Red channel

  # Convert to PIL Image
  pil_img = Image.fromarray(test_img)

  # Convert to base64
  buffer = io.BytesIO()
  pil_img.save(buffer, format='PNG')
  img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

  session.P(f"Created test image: 100x100 pixels, RGB", color='g')
  session.P(f"Base64 length: {len(img_base64)} characters", color='g')

  print()

  # Test 3: Submit image for processing
  session.P("3. Submitting image to CerviGuard API...", color='b')

  try:
    response = requests.post(
      f"{base_url}/cerviguard_submit_image",
      json={
        "image_data": img_base64,
        "metadata": {
          "patient_id": "TEST-001",
          "capture_date": "2025-01-01",
          "test_mode": True
        }
      }
    )

    session.P(f"Status: {response.status_code}", color='g' if response.status_code == 200 else 'r')
    result = response.json()

    if result.get('result', {}).get('status') == 'submitted':
      request_id = result['result']['request_id']
      session.P(f"Request ID: {request_id}", color='g')
      session.P(f"Poll endpoint: {result['result']['poll_endpoint']}", color='g')

      print()

      # Test 4: Poll for results
      session.P("4. Polling for results (loopback processing)...", color='b')

      max_attempts = 10
      attempt = 0
      result_data = None

      while attempt < max_attempts:
        attempt += 1
        time.sleep(1)  # Wait 1 second between polls

        session.P(f"  Polling attempt {attempt}/{max_attempts}...", color='y')

        response = requests.get(
          f"{base_url}/cerviguard_get_result",
          params={"request_id": request_id}
        )

        if response.status_code == 200:
          poll_result = response.json()
          status = poll_result.get('result', {}).get('status')

          if status == 'completed':
            result_data = poll_result['result']['result']
            session.P(f"  ✓ Processing completed!", color='g')
            break
          elif status == 'processing':
            session.P(f"  ⏳ Still processing...", color='y')
          elif status == 'error':
            session.P(f"  ✗ Error: {poll_result.get('result', {}).get('error')}", color='r')
            break
          else:
            session.P(f"  Unknown status: {status}", color='y')
        else:
          session.P(f"  HTTP error: {response.status_code}", color='r')
          break

      print()

      # Test 5: Display results
      if result_data:
        session.P("5. Processing Results (via Loopback Pipeline):", color='b')
        session.P("="*70, color='g')

        if result_data.get('status') == 'completed':
          img_info = result_data.get('image_info', {})
          session.P(f"  Image Dimensions:", color='g')
          session.P(f"    Width:  {img_info.get('width')} pixels", color='w')
          session.P(f"    Height: {img_info.get('height')} pixels", color='w')
          session.P(f"    Channels: {img_info.get('channels')}", color='w')
          session.P(f"    Total Pixels: {img_info.get('total_pixels'):,}", color='w')
          session.P(f"    Size: {img_info.get('size_mb')} MB", color='w')
          session.P(f"    Data Type: {img_info.get('dtype')}", color='w')
          session.P(f"    Shape: {img_info.get('shape')}", color='w')
          session.P("", color='w')
          session.P(f"  Processing Info:", color='g')
          session.P(f"    Processor Version: {result_data.get('processor_version')}", color='w')
          session.P(f"    Processed At: {result_data.get('processed_at')}", color='w')

          session.P("="*70, color='g')
          session.P("\n✓ Loopback pipeline working correctly!", color='g', boxed=True)
          session.P("  The image went through the complete flow:", color='g')
          session.P("    1. Submitted to LOCAL_SERVING_API endpoint", color='w')
          session.P("    2. Written to loopback queue (IS_LOOPBACK_PLUGIN=True)", color='w')
          session.P("    3. Loopback DCT feeds data back to pipeline", color='w')
          session.P("    4. LOCAL_SERVING_API process() reads from loopback", color='w')
          session.P("    5. Calls CERVIGUARD_IMAGE_ANALYZER serving plugin", color='w')
          session.P("    6. Result cached in LOCAL_SERVING_API", color='w')
          session.P("    7. Retrieved via API polling endpoint", color='w')
        else:
          session.P(f"  Status: {result_data.get('status')}", color='y')
          session.P(f"  Error: {result_data.get('error', 'Unknown')}", color='r')
      else:
        session.P("5. ✗ No results received after polling", color='r')
        session.P("   Check edge node logs for issues", color='y')

    else:
      session.P(f"Failed to submit image: {result}", color='r')

  except Exception as e:
    session.P(f"Error during testing: {e}", color='r')
    import traceback
    session.P(traceback.format_exc(), color='r')

  print()
  session.P("="*70)
  session.P("CerviGuard WAR Testing Complete")
  session.P("="*70 + "\n")


if __name__ == "__main__":
  # Create a session
  session = Session(silent=False)

  # Get target node from environment or use default
  # node = os.environ.get("EE_TARGET_NODE", "INSERT_YOUR_NODE_ADDRESS_HERE")
  node = "0xai_Avvuy6USRwVfbbxEG2HPiCz85mSJle3zo2MbDh5kBD-g"

  session.P(f"Deploying CerviGuard WAR Loopback Pipeline to {node}...", color='b', boxed=True)
  session.wait_for_node(node)

  # Pipeline configuration with TWO components:
  # 1. Loopback DCT (reads from queue and feeds back)
  # 2. LOCAL_SERVING_API (writes to queue, reads from queue, calls serving plugin)
  # Note: CERVIGUARD_IMAGE_ANALYZER serving plugin is called via AI_ENGINE config

  pipeline_config = {
    "NAME": "cerviguard_demo",
    "TYPE": "Loopback",  # CRITICAL: Use Loopback DCT
    "LOOPBACK_QUEUE_SIZE": 32,

    "PLUGINS": [
      # Backend API (receives images, writes to loopback, reads from loopback, calls serving)
      {
        "SIGNATURE": "LOCAL_SERVING_API",
        "INSTANCES": [
          {
            "PORT": 5002,
            "INSTANCE_ID": "cerviguard_api",
            "AI_ENGINE": "CERVIGUARD_IMAGE_ANALYZER",  # Serving plugin to use
            "LOG_REQUESTS": True,
            "RESPONSE_FORMAT": "WRAPPED",
            "RESULT_CACHE_TTL": 300,  # Keep results for 5 minutes
          }
        ]
      }

      # TODO: Add your CerviGuard UI plugin here
      # {
      #   "SIGNATURE": "YOUR_CERVIGUARD_UI_WORKER_APP",
      #   "INSTANCES": [{"INSTANCE_ID": "ui_01"}]
      # }
    ]
  }

  session.P("\nPipeline Configuration:", color='b')
  session.P(json.dumps(pipeline_config, indent=2), color='w')

  # Deploy the pipeline
  session.P("\nDeploying pipeline...", color='b')

  # Create the pipeline with Loopback data source
  pipeline = session.create_pipeline(
    node=node,
    name=pipeline_config["NAME"],
    data_source=pipeline_config["TYPE"],  # "Loopback"
    config={
      "LOOPBACK_QUEUE_SIZE": pipeline_config["LOOPBACK_QUEUE_SIZE"]
    }
  )

  # Add the LOCAL_SERVING_API plugin
  # This plugin handles everything: API endpoints, loopback, and serving plugin calls
  session.P("Adding LOCAL_SERVING_API plugin...", color='b')
  api_instance = pipeline.create_plugin_instance(
    signature='LOCAL_SERVING_API',
    instance_id='cerviguard_api',
    log_requests=True,
    response_format='WRAPPED',
    port=5082,
    ai_engine='CERVIGUARD_IMAGE_ANALYZER',  # This serving plugin runs in isolated process
    result_cache_ttl=300,
  )

  # Deploy the pipeline
  session.P("Deploying pipeline to node...", color='b')
  pipeline.deploy()

  # Wait for deployment
  session.P("Waiting for pipeline to be fully deployed...", color='b')
  time.sleep(8)

  # The API should be accessible on localhost
  # Port is configured in plugin config as 5082
  base_url = "http://localhost:5082"

  session.P(f"\n" + "="*70, color='g')
  session.P(f"CerviGuard WAR Backend Deployed!", color='g', boxed=True)
  session.P(f"="*70, color='g')
  session.P(f"API URL: {base_url}", color='g')
  session.P(f"Pipeline: {pipeline_config['NAME']}", color='g')
  session.P(f"Loopback: ENABLED", color='g')
  session.P(f"="*70 + "\n", color='g')

  # Give the server a bit more time to start
  session.P("Waiting for API server to be ready...", color='b')
  time.sleep(30)

  # Run tests
  test_cerviguard_api(base_url, session)

  # Show API endpoints
  session.P("\n" + "="*70)
  session.P("Available CerviGuard API Endpoints:")
  session.P("="*70)
  session.P(f"  POST {base_url}/cerviguard_submit_image", color='g')
  session.P(f"    - Submit cervical image for analysis", color='w')
  session.P(f"    - Body: {{'image_data': '<base64>', 'metadata': {{...}}}}", color='w')
  session.P("")
  session.P(f"  GET  {base_url}/cerviguard_get_result?request_id=<id>", color='g')
  session.P(f"    - Poll for processing results", color='w')
  session.P("")
  session.P(f"  GET  {base_url}/cerviguard_status", color='g')
  session.P(f"    - Check system status", color='w')
  session.P("="*70 + "\n")

  # Integration instructions
  session.P("Next Steps for CerviGuard UI Integration:", color='y', boxed=True)
  session.P("1. Add your CerviGuard UI worker_app to the pipeline", color='w')
  session.P("2. From UI JavaScript, call the API endpoints:", color='w')
  session.P("   - Submit image: POST /cerviguard_submit_image", color='w')
  session.P("   - Poll results: GET /cerviguard_get_result?request_id=<id>", color='w')
  session.P("3. Display the image analysis results in your UI", color='w')
  session.P("4. The serving plugin runs in isolated process for fault isolation", color='w')
  session.P("5. Later: Enhance CERVIGUARD_IMAGE_ANALYZER with actual AI model", color='w')
  session.P("")

  # Keep running
  session.P("Press Ctrl+C to stop and cleanup...", color='y')

  try:
    session.run(
      wait=True,
      close_pipelines=True
    )
  except KeyboardInterrupt:
    session.P("\nStopping and cleaning up...", color='y')

  session.P("\nCerviGuard WAR tutorial completed!", color='g', boxed=True)
