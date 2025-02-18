# load the base64 encoded swarm key into the SWARM_KEY_CONTENT_BASE64 env var
cat swarm_key_base64.txt | base64 -d > /root/.ipfs/swarm.key
cat /root/.ipfs/swarm.key