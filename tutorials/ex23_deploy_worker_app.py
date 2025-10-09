"""
ex23_deploy_worker_app.py
---------------------

This is a basic example of how to use the ratio1 SDK for deploying a worker web app
that automatically monitors a Git repository and rebuilds when changes are detected.

The example shows how to deploy a worker app that:
- Clones a Git repository into a container
- Builds and runs the application
- Monitors for new commits and automatically restarts
- Exposes the app via Cloudflare tunnel

"""
from ratio1 import Session

if __name__ == '__main__':
  
  session = Session(silent=False)

  my_node = "0xai_Avvuy6USRwVfbbxEG2HPiCz85mSJle3zo2MbDh5kBD-g"

  # Get Cloudflare token from user input
  cloudflare_token = input("Enter your Cloudflare tunnel token (or press Enter to skip): ").strip()

  if not cloudflare_token:
    session.P("Warning: No Cloudflare token provided. The app will not be accessible via tunnel.")
    cloudflare_token = None

  # VCS data for the repository to monitor
  vcs_data = {
    "PROVIDER": "github",
    "USERNAME": "vitalii-t12",  # Replace with your GitHub username
    "TOKEN": None,      # Replace with your GitHub personal access token
    "REPO_OWNER": "vitalii-t12",  # Replace with repository owner
    "REPO_NAME": "my-super-react-app",     # Replace with repository name
    "BRANCH": "main",                   # Branch to monitor for updates
  }

  # Container registry data (if using private registry)
  cr_data = {
    "SERVER": "docker.io",
    "USERNAME": None,  # Set if using private registry
    "PASSWORD": None,  # Set if using private registry
  }

  # Environment variables for the app
  env = {
    "NODE_ENV": "production",
  }

  # Container resource limits
  container_resources = {
    "cpu": 1,           # 1 CPU core
    "gpu": 0,           # No GPU
    "memory": "512m",    # 512MB memory
    # "ports": [3000],    # Container port 3000
  }

  # Build and run commands for the application
  build_and_run_commands = [
    "npm install",
    "npm run build", 
    "npm run serve"
  ]

  # (Optional) Regular volumes - mount directories from host to container
  volumes = {
    # "/host/data": "/app/data",  # Mount host directory to container
  }

  # (Optional) File volumes - create files with dynamic content and mount them
  file_volumes = {}

  app, _ = session.create_worker_web_app(
    node=my_node,
    name="ratio1_worker_webapp",
    tunnel_engine="cloudflare",
    tunnel_engine_enabled=True,
    cloudflare_token=cloudflare_token,
    
    # Worker app specific parameters
    vcs_data=vcs_data,
    image="node:22",
    build_and_run_commands=build_and_run_commands,
    cr_data=cr_data,
    env=env,
    port=4173,
    container_resources=container_resources,
    volumes=volumes,          # Directory volumes (optional)
    file_volumes=file_volumes, # File volumes with dynamic content (optional)
    vcs_poll_interval=60,     # Check for Git updates every minute
  )
  app.deploy()
  try:
    session.P("Worker webapp deployed")
    session.P("The app will automatically:")
    session.P("- Clone the repository and build the application")
    session.P("- Monitor for new commits and restart when changes are detected")
    session.P("- Expose the app via Cloudflare tunnel")
  except Exception as e:
    session.P("Error deploying worker webapp: ", e)

  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   due to the fact that this is a example/tutorial and maybe we dont want to keep the pipeline
  #   active after the session is closed we use close_pipelines=True
  #   in production, you would not need this code as the script can close 
  #   after the pipeline will be sent 
  session.wait(
    seconds=300,            # we wait the session for 5 minutes to see the app in action
    close_pipelines=True,   # we close the pipelines after the session
    close_session=True,     # we close the session after the session
  )
