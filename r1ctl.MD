# NepCTL Manual

## Overview
**NepCTL** (ratio1 Edge Protocol Command-Line Tool) is a CLI utility for interacting with a decentralized network of nodes running ratio1 Edge Protocol. It provides commands to query network nodes, configure the client, and manage nodes directly from the terminal.

## Installation

Installation is straightforward using `pip` so make sure you have python 3.9+ and pip installed on your system.

```bash
pip install ratio1
```

Following the instalation make sure you edit `~/.ratio1/config` file and put the correct mqtt broker credentials, particularly `EE_MQTT_USER` and `EE_MQTT` which are the username and password for the mqtt broker.

```plaintext
EE_MQTT_HOST=r9092118.ala.eu-central-1.emqxsl.com
EE_MQTT_PORT=8883
EE_MQTT_USER=
EE_MQTT=

EE_SECURED=true

EE_TARGET_NODE=
```


### General Usage
```bash
nepctl [COMMAND] [OPTIONS]
```

### Available Commands
- **`get`**: Query nodes or supervisors.
- **`config`**: Display and manage configuration settings.
- **`restart`**: Restart a specific node.
- **`shutdown`**: Shutdown a specific node.

## Commands and Options

### `get`
Query nodes or supervisors in the network.

#### `get nodes`
Retrieve information about network nodes.

**Options**:
- `--all`: Get all known nodes.
- `--online`: Get only online nodes.
- `--peered`: Get only peered nodes - ie the nodes that allow the current client to connect to them and give them workloads
- `--supervisor="addr"`: Query nodes using a specific supervisor address.
- `--eth`: Use ETH addresses instead of the default Ratio1 addresses.

**Examples**:
```bash
# Get all known nodes:
nepctl get nodes --all

# Get online nodes using a specific supervisor:
nepctl get nodes --online --supervisor="Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6"
```

#### Using ETH addresses

Due to the fact that oracles use the ETH version of the node and SDK addresses we need to use the ETH version of the addresses when querying the oracles. T

**Examples**:
```bash
# Get all known nodes using ETH addresses:
nepctl get nodes --online --eth
```


#### `get supervisors`
Retrieve information about supervisors in the network.

**Examples**:
```bash
# Get all supervisors:
nepctl get avail <node_eth_address>
```

#### `get avail <node_eth_address>`
Retrieve availability of the node throughout a range of epochs from the network oracles.

**Options**:
- `--start`: The epoch to start from(default=1).
- `--end`: The epoch to end at (if not provided the last finished epoch will be used).
- `--rounds`: How many requests to make to the network oracles (default=1).
- `--json`: Get the raw json output from the request to the network oracles(default=false). In case of multiple rounds this will be disabled.

**Examples**:
```bash
# Get availabilities for all the finished epochs:
nepctl get avail <node_eth_address>

# Get availabilities for the first 10 epochs:
nepctl get avail <node_eth_address> --end=10

# Get availabilities for epochs 20 to 25 for 5 rounds:
nepctl get avail <node_eth_address> --start=20 --end=25 --rounds=5

# Get full json output for epochs 12 to 15:
nepctl get avail <node_eth_address> --start=12 --end=15 --json
```

### `config`
Manage client configuration settings.

#### `config show`
Display the current configuration, including its location and client address.

**Examples**:
```bash
# Show current configuration:
nepctl config show
```

#### `config reset`
Reset the configuration to its default values.

**Examples**:
```bash
# Reset configuration:
nepctl config reset
```

#### `config addr`
Display the current client address.

**Examples**:
```bash
# Show client address:
nepctl config addr
```

### `restart`
Restart a specific node.


**Options**:
- `node`: The address of the node to restart.

**Examples**:
```bash
# Restart a node:
nepctl restart --node="0xai_AleLPKqUHV-iPc-76-rUvDkRWW4dFMIGKW1xFVcy65nH"
```

### `shutdown`
Shutdown a specific node.

**Options**:
- `node`: The address of the node to shutdown.

**Examples**:
```bash
# Shutdown a node:
nepctl shutdown --node="0xai_AhsgqiqJZzav1OHUlam7K9tZWysPv1QWcZU0AhFJ6wsJ"
```

## Example Outputs

### `get nodes`
```plaintext
Network full map reported by <0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6>:
                                              Address             Alias      Seen ago   Last state          Last probe   Zone  Supervisor
0   0xai_AkSf-Ocgg2ykXwF-QvsA3VRDbV7pK02T2vpYZeelkgVb      40ffd6d6a742      08:10:56  LOST STATUS 2024-12-23 17:47:00  UTC+2       False
...
```

### `get supervisors`
```plaintext
Supervisors reported by <0xai_AleLPKqUHV-iPc-76-rUvDkRWW4dFMIGKW1xFVcy65nH>:
                                             Address      Alias  Seen ago Last state          Last probe   Zone  Supervisor
0  0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6      nen-2  00:00:02     ONLINE 2024-12-24 02:06:03  UTC+2        True
...
```

### `config show`
```plaintext
NEP SDK folder: /root/.ratio1
SDK Client address: 0xai_AjcIThkOqrPlp35-S8czHUOV-y4mnhksnLs8NGjTbmty
Current configuration (/root/.ratio1/config):

EE_MQTT_HOST=r9092118.ala.eu-central-1.emqxsl.com
EE_MQTT_PORT=8883
EE_MQTT_USER=coreeratio1
EE_MQTT=<password>
...
```

## Notes
- Use `--verbose` or `-v` for detailed output on any command. This can be rather useful for debugging purposes.
- For help with any command or subcommand, append `-h` (e.g., `nepctl get nodes -h`).

