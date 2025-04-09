# Ratio1 SDK

Welcome to the **Ratio1 SDK** repository, formerly known as the **ratio1 SDK**. The Ratio1 SDK is a crucial component of the Ratio1 ecosystem, designed to facilitate interactions, development, and deployment of jobs within the Ratio1 network. By enabling low-code development, the SDK allows developers to build and deploy end-to-end AI (and beyond) cooperative application pipelines seamlessly within the Ratio1 Edge Nodes ecosystem.

## Overview

The **Ratio1 SDK** is engineered to enhance the Ratio1 protocol and ecosystem, aiming to improve the functionality and performance of the Ratio1 Edge Node through dedicated research and community contributions. This SDK serves as an essential tool for developers looking to integrate their applications with the Ratio1 network, enabling them to leverage the decentralized, secure, and privacy-preserving capabilities of Ratio1 Edge Nodes.

Key functionalities of the Ratio1 SDK include:

- **Job Interactions**: Facilitate the development and management of computation tasks within the Ratio1 network.
- **Development Tools**: Provide low-code solutions for creating and deploying AI-driven application pipelines.
- **Ecosystem Integration**: Seamlessly integrate with Ratio1 Edge Nodes to utilize their computational resources effectively.
- **Collaboration and Deployment**: Enable cooperative application development and deployment across multiple edge nodes within the Ratio1 ecosystem.

Unlike the Ratio1 Core Packages, which are intended solely for protocol and ecosystem enhancements and are not meant for standalone installation, the Ratio1 SDK is designed for both client-side development and sending workloads to Ratio1 Edge Nodes, making it an indispensable tool for developers within the ecosystem.

## The `nepctl` CLI Tool

Our SDK has a CLI tool called `nepctl` that allows you to interact with the Ratio1 network. You can use it to query nodes, configure the client, and manage nodes directly from the terminal. The `nepctl` tool is a powerful utility that simplifies network interactions and provides a seamless experience for developers.

For more information on the `nepctl` CLI tool, please refer to the [nepctl](nepctl.md) documentation.

## Dependencies

The Ratio1 SDK relies on several key packages to function effectively. These dependencies are automatically managed when installing the SDK via pip:

- `pika`
- `paho-mqtt`
- `numpy`
- `pyopenssl>=23.0.0`
- `cryptography>=39.0.0`
- `python-dateutil`
- `pyaml`

## Installation

Installing the Ratio1 SDK is straightforward and is intended for development and integration into your projects. Use the following pip commands to install the SDK:

### Standard Installation

To install the Ratio1 SDK, run:

```shell
pip install ratio1_sdk --upgrade
```

### Development Installation

For development purposes, you can clone the repository and set up the SDK in an editable mode:

```shell
git clone https://github.com/Ratio1/ratio1_sdk
cd ratio1_sdk
pip install -e .
```

This allows you to make modifications to the SDK and have them reflected immediately without reinstalling.

## Documentation

Comprehensive documentation for the Ratio1 SDK is currently a work in progress. Minimal documentation is available here, with detailed code examples located in the `tutorials` folder within the project's repository. We encourage developers to explore these examples to understand the SDK's capabilities and integration methods.

## Quick Start Guides

Starting with version 2.6+, the Ratio1 SDK automatically performs self-configuration using **dAuth**—the Ratio1 decentralized self-authentication system. To begin integrating with the Ratio1 network, follow these steps:

### 1. Start a Local Edge Node (testnet)

Launch a local Ratio1 Edge Node using Docker:

```bash
docker run -d --name=r1node ratio1/edge_node:testnet
```

if you want to have a persistent volume for the node, you can use the following command:

```bash
docker run -d --name=r1node --rm --pull=always -v r1vol:/edge_node/_local_cache ratio1/edge_node:testnet
```
This way the node will store its data in the `r1vol` volume, and you can stop and start the node without losing data you might have stored in the node via deployed jobs from your SDK. We also added the `--pull=always` flag to ensure that the latest version of the node is always pulled from the Docker Hub.

After a few seconds, the node will be online. Retrieve the node's address by running:

```bash
docker exec r1node get_node_info
```

The output will resemble:

```json
{
  "address": "0xai_A2pPf0lxZSZkGONzLOmhzndncc1VvDBHfF-YLWlsrG9m",
  "alias": "5ac5438a2775",
  "eth_address": "0xc440cdD0BBdDb5a271de07d3378E31Cb8D9727A5",
  "version_long": "v2.5.36 | core v7.4.23 | SDK 2.6.15",
  "version_short": "v2.5.36",
  "info": {
    "whitelist": []
  }
}
```

As you can see, the node is online and NOT ready to accept workloads due to the fact that it has no whitelisted clients. To whitelist your client, you need to use the `add_allowed` command:

```bash
docker exec r1node add_allowed <address> [<alias>]
```

where `<address>` is the address of your client and `<alias>` is an optional alias for your client.
A example of whitelisting a client is:

```bash
docker exec r1node add_allowed 0xai_AthDPWc_k3BKJLLYTQMw--Rjhe3B6_7w76jlRpT6nDeX some-node-alias
```

You will then receive a response similar to:

```json
{
  "address": "0xai_A2pPf0lxZSZkGONzLOmhzndncc1VvDBHfF-YLWlsrG9m",
  "alias": "5ac5438a2775",
  "eth_address": "0xc440cdD0BBdDb5a271de07d3378E31Cb8D9727A5",
  "version_long": "v2.5.36 | core v7.4.23 | SDK 2.6.15",
  "version_short": "v2.5.36",
  "info": {
    "whitelist": [
      "0xai_AthDPWc_k3BKJLLYTQMw--Rjhe3B6_7w76jlRpT6nDeX"
    ]
  }
}
```


### 2. Develop and Deploy Jobs

Use the SDK to develop and send workloads to the Edge Nodes. Below are examples of both local and remote execution.

## Examples

### Local Execution

This example demonstrates how to find all 168 prime numbers in the interval 1 - 1000 using local execution. The code leverages multiple threads to perform prime number generation efficiently.

```python
import numpy as np
from concurrent.futures import ThreadPoolExecutor

def local_brute_force_prime_number_generator():
    def is_prime(n):
        if n <= 1:
            return False
        for i in range(2, int(np.sqrt(n)) + 1):
            if n % i == 0:
                return False
        return True

    random_numbers = np.random.randint(1, 1000, 20)

    thread_pool = ThreadPoolExecutor(max_workers=4)
    are_primes = list(thread_pool.map(is_prime, random_numbers))

    prime_numbers = []
    for i in range(len(random_numbers)):
        if are_primes[i]:
            prime_numbers.append(random_numbers[i])

    return prime_numbers

if __name__ == "__main__":
    found_so_far = []
    print_step = 0

    while len(found_so_far) < 168:
        # Compute a batch of prime numbers
        prime_numbers = local_brute_force_prime_number_generator()

        # Keep only the new prime numbers
        for prime_number in prime_numbers:
            if prime_number not in found_so_far:
                found_so_far.append(prime_number)

        # Show progress
        if print_step % 50 == 0:
            print("Found so far: {}:  {}\n".format(len(found_so_far), sorted(found_so_far)))

        print_step += 1

    # Show final result
    print("Found so far: {}:  {}\n".format(len(found_so_far), sorted(found_so_far)))
```

### Remote Execution

To accelerate prime number discovery, this example demonstrates deploying the task across multiple edge nodes within the Ratio1 network. Minimal code changes are required to transition from local to remote execution.

#### 1. Modify the Prime Number Generator

```python
from ratio1_sdk import CustomPluginTemplate

def remote_brute_force_prime_number_generator(plugin: CustomPluginTemplate):
    def is_prime(n):
        if n <= 1:
            return False
        for i in range(2, int(plugin.np.sqrt(n)) + 1):
            if n % i == 0:
                return False
        return True

    random_numbers = plugin.np.random.randint(1, 1000, 20)
    are_primes = plugin.threadapi_map(is_prime, random_numbers, n_threads=4)

    prime_numbers = []
    for i in range(len(random_numbers)):
        if are_primes[i]:
            prime_numbers.append(random_numbers[i])

    return prime_numbers
```

#### 2. Connect to the Network and Select a Node

```python
from ratio1_sdk import Session
from time import sleep

def on_heartbeat(session: Session, node: str, heartbeat: dict):
    session.P("{} is online".format(node))
    return

if __name__ == '__main__':
    session = Session(
        on_heartbeat=on_heartbeat
    )

    # Run the program for 15 seconds to detect online nodes
    sleep(15)

    # Retrieve and select an online node
    node = "0xai_A8SY7lEqBtf5XaGyB6ipdk5C30vSf3HK4xELp3iplwLe"  # ratio1-1
```

#### 3. Deploy the Distributed Job

```python
from ratio1_sdk import DistributedCustomCodePresets as Presets

_, _ = session.create_chain_dist_custom_job(
    node=node,
    main_node_process_real_time_collected_data=Presets.PROCESS_REAL_TIME_COLLECTED_DATA__KEEP_UNIQUES_IN_AGGREGATED_COLLECTED_DATA,
    main_node_finish_condition=Presets.FINISH_CONDITION___AGGREGATED_DATA_MORE_THAN_X,
    main_node_finish_condition_kwargs={"X": 167},
    main_node_aggregate_collected_data=Presets.AGGREGATE_COLLECTED_DATA___AGGREGATE_COLLECTED_DATA,
    nr_remote_worker_nodes=2,
    worker_node_code=remote_brute_force_prime_number_generator,
    on_data=locally_process_partial_results,
    deploy=True
)
```

#### 4. Close the Session Upon Completion

```python
# Wait until the finished flag is set to True
session.run(wait=lambda: not finished, close_pipelines=True)
```

## Project Financing Disclaimer

This project incorporates open-source components developed with the support of financing grants **SMIS 143488** and **SMIS 156084**, provided by the Romanian Competitiveness Operational Programme. We extend our sincere gratitude for this support, which has been instrumental in advancing our work and enabling us to share these resources with the community.

The content and information within this repository are solely the responsibility of the authors and do not necessarily reflect the views of the funding agencies. The grants have specifically supported certain aspects of this open-source project, facilitating broader dissemination and collaborative development.

For any inquiries regarding the funding and its impact on this project, please contact the authors directly.

## License

This project is licensed under the **Apache 2.0 License**. For more details, please refer to the [LICENSE](LICENSE) file.

## Contact

For more information, visit our website at [https://ratio1.ai](https://ratio1.ai) or reach out to us via email at [support@ratio1.ai](mailto:support@ratio1.ai).

## Citation

If you use the Ratio1 SDK in your research or projects, please cite it as follows:

```bibtex
@misc{Ratio1SDK,
  author       = {Ratio1.AI},
  title        = {Ratio1 SDK},
  year         = {2024-2025},
  howpublished = {\url{https://github.com/Ratio1/ratio1_sdk}},
}
```

```bibtex
@misc{Ratio1EdgeNode,
  author = {Ratio1.AI},
  title = {Ratio1: Edge Node},
  year = {2024-2025},
  howpublished = {\url{https://github.com/Ratio1/edge_node}},
}
```
