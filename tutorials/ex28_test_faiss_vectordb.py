"""
test_faiss_vectordb.py
---------------------------------

Deploy the TestFaissVectordb plugin on a local edge node and exercise its
FAISS vectordb endpoints via HTTP requests.

Usage:
  python test_faiss_vectordb.py

  # or with a specific node address:
  EE_TARGET_NODE=0xai_... python test_faiss_vectordb.py
"""

import os
import time
import requests

from ratio1 import Session

def test_endpoints(base_url: str):
  """Run a sequence of tests against the deployed plugin."""
  print(f"\n{'='*60}")
  print(f"Testing FAISS vectordb plugin at: {base_url}")
  print(f"{'='*60}\n")

  # Test 1: Status
  # Clean up any leftover contexts from previous runs
  print("--- Setup: Reset test contexts ---")
  for ctx in ["test1", "test2"]:
    requests.post(f"{base_url}/reset_context", json={"context": ctx})
  print("  Done\n")

  print("--- Test 1: GET /status ---")
  r = requests.get(f"{base_url}/status")
  print(f"  Response: {r.json()}")
  assert r.status_code == 200
  print("  PASS\n")

  # Test 2: Add documents
  print("--- Test 2: POST /add_docs ---")
  docs = [
    "The quick brown fox jumps over the lazy dog",
    "Machine learning is a subset of artificial intelligence",
    "FAISS is a library for efficient similarity search",
    "Docker containers provide isolated environments",
    "Python is a popular programming language",
  ]
  r = requests.post(f"{base_url}/add_docs", json={
    "context": "test1",
    "documents": docs,
  })
  print(f"  Response: {r.json()}")
  assert r.status_code == 200
  data = r.json()
  # handle wrapped response format
  if "result" in data:
    data = data["result"]
  assert data["added"] == 5
  assert data["total"] == 5
  print("  PASS\n")

  # Test 3: Search — exact match
  print("--- Test 3: POST /search (exact match) ---")
  r = requests.post(f"{base_url}/search", json={
    "query": "FAISS is a library for efficient similarity search",
    "context": "test1",
    "k": 3,
  })
  print(f"  Response: {r.json()}")
  assert r.status_code == 200
  data = r.json()
  if "result" in data:
    data = data["result"]
  assert data["results"][0]["text"] == "FAISS is a library for efficient similarity search"
  assert data["results"][0]["score"] > 0.99
  print("  PASS\n")

  # Test 4: List contexts
  print("--- Test 4: GET /list_contexts ---")
  r = requests.get(f"{base_url}/list_contexts")
  print(f"  Response: {r.json()}")
  assert r.status_code == 200
  print("  PASS\n")

  # Test 5: Add docs to second context
  print("--- Test 5: POST /add_docs (second context) ---")
  r = requests.post(f"{base_url}/add_docs", json={
    "context": "test2",
    "documents": ["Separate context document"],
  })
  print(f"  Response: {r.json()}")
  assert r.status_code == 200
  print("  PASS\n")

  # Test 6: Verify context isolation
  print("--- Test 6: GET /list_contexts (verify isolation) ---")
  r = requests.get(f"{base_url}/list_contexts")
  data = r.json()
  if "result" in data:
    data = data["result"]
  print(f"  Response: {data}")
  assert data["contexts"]["test1"] == 5
  assert data["contexts"]["test2"] == 1
  print("  PASS\n")

  # Test 7: Search non-existent context
  print("--- Test 7: POST /search (non-existent context) ---")
  r = requests.post(f"{base_url}/search", json={
    "query": "anything",
    "context": "does_not_exist",
    "k": 1,
  })
  print(f"  Response: {r.json()}")
  assert r.status_code == 200
  print("  PASS\n")

  # Test 8: Reset context
  print("--- Test 8: POST /reset_context ---")
  r = requests.post(f"{base_url}/reset_context", json={"context": "test1"})
  print(f"  Response: {r.json()}")
  assert r.status_code == 200
  print("  PASS\n")

  # Test 9: Verify reset
  print("--- Test 9: GET /status (verify reset) ---")
  r = requests.get(f"{base_url}/status")
  data = r.json()
  if "result" in data:
    data = data["result"]
  print(f"  Response: {data}")
  assert "test1" not in data["contexts"]
  print("  PASS\n")

  print(f"{'='*60}")
  print("All tests passed!")
  print(f"{'='*60}")


if __name__ == "__main__":
  session = Session(silent=False)

  node = "0xai_A7H8Sp6peXqx7ES_3chDXRnWl-aUfZ07PyY25if-l95m"

  session.P(f"Waiting for node {node}...")
  session.wait_for_node(node)

  pipeline, instance = session.create_web_app(
    node=node,
    name="test_faiss_vectordb",
    signature="TEST_FAISS_VECTORDB",
    tunnel_engine="ngrok",
    endpoints=[],
    NGROK_PROTOCOL="http",
  )

  url = pipeline.deploy(verbose=True)
  session.P(f"Plugin deployed at: {url}", color='g')

  # Wait for the webapp to be ready
  session.P("Waiting 15s for plugin to initialize...")
  time.sleep(15)

  try:
    test_endpoints(url)
  except Exception as e:
    session.P(f"Test failed: {e}", color='r')
    import traceback
    traceback.print_exc()
  finally:
    # Clean up test data so we don't leave the node dirty
    session.P("Cleaning up test contexts...")
    for ctx in ["test1", "test2"]:
      try:
        requests.post(f"{url}/reset_context", json={"context": ctx})
      except Exception:
        pass
    session.P("Cleanup done.")

  session.run(
    wait=False,
    close_pipelines=True,
  )
