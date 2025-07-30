class EvmNetData:
  MAINNET = 'mainnet'
  TESTNET = 'testnet'
  DEVNET = 'devnet'

  DAUTH_URL_KEY = 'EE_DAUTH_URL'
  DAUTH_ND_ADDR_KEY = 'EE_DAUTH_ND_ADDR'
  DAUTH_RPC_KEY = 'EE_DAUTH_RPC'
  DAUTH_R1_ADDR_KEY = 'EE_DAUTH_R1_ADDR'
  DAUTH_MND_ADDR_KEY = 'EE_DAUTH_MND_ADDR'
  DAUTH_PROXYAPI_ADDR_KEY = 'EE_DAUTH_PROXYAPI_ADDR'
  DAUTH_POAI_MANAGER_KEY = 'EE_DAUTH_POAI_MANAGER'
  
  DAUTH_CONTROLLER_ADDR_KEY = 'EE_DAUTH_CONTROLLER_ADDR'  
  DAUTH_GET_ORACLES_ABI = 'EE_DAUTH_GET_ORACLES_ABI'
  
  EE_GENESIS_EPOCH_DATE_KEY = 'EE_GENESIS_EPOCH_DATE'
  EE_EPOCH_INTERVALS_KEY = 'EE_EPOCH_INTERVALS'
  EE_EPOCH_INTERVAL_SECONDS_KEY = 'EE_EPOCH_INTERVAL_SECONDS'
  
  EE_SUPERVISOR_MIN_AVAIL_PRC_KEY = 'EE_SUPERVISOR_MIN_AVAIL_PRC'

  EE_ORACLE_API_URL_KEY = 'EE_ORACLE_API_URL'
  EE_DEEPLOY_API_URL_KEY = 'EE_DEEPLOY_API_URL'
# endclass EvmNetData


# Below are basic parameters for plugins that do not interact directly with the blockchain.
class EvmNetConstants:
  EE_NET_MON_01_SUPERVISOR_LOG_TIME_KEY = 'EE_NET_MON_01_SUPERVISOR_LOG_TIME'
  NET_CONFIG_MONITOR_SHOW_EACH_KEY = 'NET_CONFIG_MONITOR_SHOW_EACH'
  SEED_NODES_ADDRESSES_KEY = 'SEED_NODES_ADDRESSES' # This is a list of seed nodes for the network, used for initial connections.
# endclass EvmNetConstants


_DAUTH_ABI_IS_NODE_ACTIVE = [{
  "inputs": [
    {
      "internalType": "address",
      "name": "nodeAddress",
      "type": "address"
    }
  ],
  "name": "isNodeActive",
  "outputs": [
    {
      "internalType": "bool",
      "name": "",
      "type": "bool"
    }
  ],
  "stateMutability": "view",
  "type": "function"
}]


_DAUTH_ABI_GET_ORACLES = [{
  "inputs": [],
  "name": "getOracles",
  "outputs": [
    {
      "internalType": "address[]",
      "name": "",
      "type": "address[]"
    }
  ],
  "stateMutability": "view",
  "type": "function"
}]


_DAUTH_ABI_GET_SIGNERS_deprecated = [{
  "inputs": [],
  "name": "getSigners",
  "outputs": [
    {
      "internalType": "address[]",
      "name": "",
      "type": "address[]"
    }
  ],
  "stateMutability": "view",
  "type": "function"
}]


_GET_NODE_INFO_ABI = [
  {
      "inputs": [
        {
          "internalType": "address",
          "name": "node",
          "type": "address"
        }
      ],
      "name": "getNodeLicenseDetails",
      "outputs": [
        {
          "components": [
            {
              "internalType": "enum LicenseType",
              "name": "licenseType",
              "type": "uint8"
            },
            {
              "internalType": "uint256",
              "name": "licenseId",
              "type": "uint256"
            },
            {
              "internalType": "address",
              "name": "owner",
              "type": "address"
            },
            {
              "internalType": "address",
              "name": "nodeAddress",
              "type": "address"
            },
            {
              "internalType": "uint256",
              "name": "totalAssignedAmount",
              "type": "uint256"
            },
            {
              "internalType": "uint256",
              "name": "totalClaimedAmount",
              "type": "uint256"
            },
            {
              "internalType": "uint256",
              "name": "lastClaimEpoch",
              "type": "uint256"
            },
            {
              "internalType": "uint256",
              "name": "assignTimestamp",
              "type": "uint256"
            },
            {
              "internalType": "address",
              "name": "lastClaimOracle",
              "type": "address"
            },
            {
              "internalType": "bool",
              "name": "isBanned",
              "type": "bool"
            }
          ],
          "internalType": "struct LicenseDetails",
          "name": "",
          "type": "tuple"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    }
]


_GET_WALLET_NODES = [
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "wallet",
          "type": "address"
        }
      ],
      "name": "getWalletNodes",
      "outputs": [
        {
          "internalType": "address[]",
          "name": "nodes",
          "type": "address[]"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
]

_GET_ADDRESSES_BALANCES = [
  {
    "inputs": [
      {
        "internalType": "address[]",
        "name": "addresses",
        "type": "address[]"
      }
    ],
    "name": "getAddressesBalances",
    "outputs": [
      {
        "components": [
          {
            "internalType": "address",
            "name": "addr",
            "type": "address"
          },
          {
            "internalType": "uint256",
            "name": "ethBalance",
            "type": "uint256"
          },
          {
            "internalType": "uint256",
            "name": "r1Balance",
            "type": "uint256"
          }
        ],
        "internalType": "struct AddressBalances[]",
        "name": "balances",
        "type": "tuple[]"
      }
    ],
    "stateMutability": "view",
    "type": "function"
  }
]

_GET_JOB_DETAILS_ABI = [
  {
    "inputs": [
      {
        "internalType": "uint256",
        "name": "jobId",
        "type": "uint256"
      }
    ],
    "name": "getJobDetails",
    "outputs": [
      {
        "components": [
          {
            "internalType": "uint256",
            "name": "id",
            "type": "uint256"
          },
          {
            "internalType": "uint256",
            "name": "requestTimestamp",
            "type": "uint256"
          },
          {
            "internalType": "uint256",
            "name": "startTimestamp",
            "type": "uint256"
          },
          {
            "internalType": "uint256",
            "name": "lastNodesChangeTimestamp",
            "type": "uint256"
          },
          {
            "internalType": "uint256",
            "name": "jobType",
            "type": "uint256"
          },
          {
            "internalType": "uint256",
            "name": "pricePerEpoch",
            "type": "uint256"
          },
          {
            "internalType": "uint256",
            "name": "lastExecutionEpoch",
            "type": "uint256"
          },
          {
            "internalType": "uint256",
            "name": "numberOfNodesRequested",
            "type": "uint256"
          },
          {
            "internalType": "int256",
            "name": "balance",
            "type": "int256"
          },
          {
            "internalType": "uint256",
            "name": "lastAllocatedEpoch",
            "type": "uint256"
          },
          {
            "internalType": "address[]",
            "name": "activeNodes",
            "type": "address[]"
          },
          {
            "internalType": "address",
            "name": "escrowAddress",
            "type": "address"
          },
          {
            "internalType": "address",
            "name": "escrowOwner",
            "type": "address"
          }
        ],
        "internalType": "struct JobWithAllDetails",
        "name": "",
        "type": "tuple"
      }
    ],
    "stateMutability": "view",
    "type": "function"
  }
]

# A minimal ERC20 ABI for balanceOf, transfer, and decimals functions.
_ERC20_ABI = [
  {
      "constant": True,
      "inputs": [{"name": "_owner", "type": "address"}],
      "name": "balanceOf",
      "outputs": [{"name": "balance", "type": "uint256"}],
      "payable": False,
      "stateMutability": "view",
      "type": "function"
  },
  {
      "constant": False,
      "inputs": [
          {"name": "_to", "type": "address"},
          {"name": "_value", "type": "uint256"}
      ],
      "name": "transfer",
      "outputs": [{"name": "success", "type": "bool"}],
      "payable": False,
      "stateMutability": "nonpayable",
      "type": "function"
  },
  {
      "constant": True,
      "inputs": [],
      "name": "decimals",
      "outputs": [{"name": "", "type": "uint8"}],
      "payable": False,
      "stateMutability": "view",
      "type": "function"
  }
]


# Here are all the constants used for blockchain interaction for each network.
EVM_NET_DATA = {
  EvmNetData.MAINNET: {
    EvmNetData.DAUTH_URL_KEY                    : "https://dauth.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_CONTROLLER_ADDR_KEY        : "0x90dA5FdaA92edDC80FB73114fb7FE7D97f2be017",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0xE658DF6dA3FB5d4FBa562F1D5934bd0F9c6bd423",
    EvmNetData.DAUTH_R1_ADDR_KEY                : "0x6444C6c2D527D85EA97032da9A7504d6d1448ecF",
    EvmNetData.DAUTH_MND_ADDR_KEY               : "0x0C431e546371C87354714Fcc1a13365391A549E2",
    EvmNetData.DAUTH_PROXYAPI_ADDR_KEY          : "0xa2fDD4c7E93790Ff68a01f01AA789D619F12c6AC",
    EvmNetData.DAUTH_POAI_MANAGER_KEY           : "0xTODO",
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-mainnet.public.blastapi.io",
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-05-23 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 24,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.96,
    EvmNetData.EE_ORACLE_API_URL_KEY            : "https://oracle.ratio1.ai",
    EvmNetData.EE_DEEPLOY_API_URL_KEY           : "https://deeploy-api.ratio1.ai",
    EvmNetData.DAUTH_GET_ORACLES_ABI            : _DAUTH_ABI_GET_ORACLES,
  },

  EvmNetData.TESTNET: {
    EvmNetData.DAUTH_URL_KEY                    : "https://testnet-dauth.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_CONTROLLER_ADDR_KEY        : "0x63BEC1B3004154698830C7736107E7d3cfcbde79",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0x18E86a5829CA1F02226FA123f30d90dCd7cFd0ED",
    EvmNetData.DAUTH_R1_ADDR_KEY                : "0xCC96f389F45Fc08b4fa8e2bC4C7DA9920292ec64",
    EvmNetData.DAUTH_MND_ADDR_KEY               : "0xa8d7FFCE91a888872A9f5431B4Dd6c0c135055c1",
    EvmNetData.DAUTH_PROXYAPI_ADDR_KEY          : "0xd1c7Dca934B37FAA402EB2EC64F6644d6957bE3b",
    EvmNetData.DAUTH_POAI_MANAGER_KEY           : "0xTODO",
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-sepolia.public.blastapi.io",      
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-05-23 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 24,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.6,
    EvmNetData.EE_ORACLE_API_URL_KEY            : "https://testnet-oracle.ratio1.ai",
    EvmNetData.EE_DEEPLOY_API_URL_KEY           : "https://testnet-deeploy-api.ratio1.ai",
    EvmNetData.DAUTH_GET_ORACLES_ABI            : _DAUTH_ABI_GET_ORACLES,
  },

  
  EvmNetData.DEVNET : {
    EvmNetData.DAUTH_URL_KEY                    : "https://devnet-dauth.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_CONTROLLER_ADDR_KEY        : "0x46fB56B7499925179d81380199E238f7AE75857B",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0x90025B92240E3070d5CdcB3f44D6411855c55a73",
    EvmNetData.DAUTH_R1_ADDR_KEY                : "0x277CbD0Cf25F4789Bc04035eCd03d811FAf73691",
    EvmNetData.DAUTH_MND_ADDR_KEY               : "0x17B8934dc5833CdBa1eF42D13D65D677C4727748",
    EvmNetData.DAUTH_PROXYAPI_ADDR_KEY          : "0xFcF04c9A67330431Af75a546615E4881BD8bdC78",
    EvmNetData.DAUTH_POAI_MANAGER_KEY           : "0x9A41f43494fCD592577228fE8E4014f2D75d2aa3",
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-sepolia.public.blastapi.io",
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-06-30 07:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 1,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.6,
    EvmNetData.EE_ORACLE_API_URL_KEY            : "https://devnet-oracle.ratio1.ai",
    EvmNetData.EE_DEEPLOY_API_URL_KEY           : "https://devnet-deeploy-api.ratio1.ai",
    EvmNetData.DAUTH_GET_ORACLES_ABI            : _DAUTH_ABI_GET_ORACLES,
  },
}


# Here are all the constants used for anything unrelated to blockchain interaction
# (e.g. logging parameters for certain admin plugins).
EVM_NET_CONSTANTS = {
  EvmNetData.MAINNET: {
    EvmNetConstants.EE_NET_MON_01_SUPERVISOR_LOG_TIME_KEY: None,  # Default is None, meaning no logging.
    EvmNetConstants.NET_CONFIG_MONITOR_SHOW_EACH_KEY: None,  # Default is None, meaning no periodic logging.
    EvmNetConstants.SEED_NODES_ADDRESSES_KEY: [
      "0xai_Aj1FpPQHISEBelp-tQ8cegwk434Dcl6xaHmuhZQT74if",  # r1s-01
      "0xai_AzySbyf7ggk1UOWkujAy6GFFmDy2MID8Jz7gqxZaDhy8",  # r1s-02
      "0xai_Apkb2i2m8zy8h2H4zAhEnZxgV1sLKAPhjD29B1I_I9z7",  # r1s-03
      "0xai_AgNhMIJZkkWdrTjnmrqdOa6hzAXkoXPNV4Zbvbm_piYJ",  # r1s-04
    ],
  },
  EvmNetData.TESTNET: {
    EvmNetConstants.EE_NET_MON_01_SUPERVISOR_LOG_TIME_KEY: 120,  # Log every 2 minutes.
    EvmNetConstants.NET_CONFIG_MONITOR_SHOW_EACH_KEY: 120,  # Show every 2 minutes.
    EvmNetConstants.SEED_NODES_ADDRESSES_KEY: [
      "0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6",  # tr1s-01
      "0xai_A61eKDV1otIH6uWy3zDlbJNJUWayp1jAsirOuYxztf82",  # tr1s-02
    ],
  },
  EvmNetData.DEVNET: {
    EvmNetConstants.EE_NET_MON_01_SUPERVISOR_LOG_TIME_KEY: 60,  # Log every minute.
    EvmNetConstants.NET_CONFIG_MONITOR_SHOW_EACH_KEY: 60,  # Show every minute.
    EvmNetConstants.SEED_NODES_ADDRESSES_KEY: [
      "0xai_AhIQz47-2dpbncDTODXcP7_cByr0_CI9VEB1dCXnbbG7",  # dr1s-01
      "0xai_AgnygSlY8BwnmaCj6mItg36JHlG_Lh3UqqFaTPbuNzy0",  # dr1s-02
    ],
  },
}

class EVM_ABI_DATA:
  GET_NODE_INFO = _GET_NODE_INFO_ABI
  GET_WALLET_NODES = _GET_WALLET_NODES
  GET_ADDRESSES_BALANCES = _GET_ADDRESSES_BALANCES
  IS_NODE_ACTIVE = _DAUTH_ABI_IS_NODE_ACTIVE
  GET_JOB_DETAILS = _GET_JOB_DETAILS_ABI
  ERC20_ABI = _ERC20_ABI
  