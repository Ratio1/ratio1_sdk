class EvmNetData:
  DAUTH_URL_KEY = 'EE_DAUTH_URL'
  DAUTH_ND_ADDR_KEY = 'EE_DAUTH_ND_ADDR'
  DAUTH_RPC_KEY = 'EE_DAUTH_RPC'
  DAUTH_R1_ADDR_KEY = 'EE_DAUTH_R1_ADDR'
  DAUTH_MND_ADDR_KEY = 'EE_DAUTH_MND_ADDR'
  DAUTH_PROXYAPI_ADDR_KEY = 'EE_DAUTH_PROXYAPI_ADDR'
  
  DAUTH_CONTROLLER_ADDR_KEY = 'EE_DAUTH_CONTROLLER_ADDR'  
  DAUTH_GET_ORACLES_ABI = 'EE_DAUTH_GET_ORACLES_ABI'
  
  EE_GENESIS_EPOCH_DATE_KEY = 'EE_GENESIS_EPOCH_DATE'
  EE_EPOCH_INTERVALS_KEY = 'EE_EPOCH_INTERVALS'
  EE_EPOCH_INTERVAL_SECONDS_KEY = 'EE_EPOCH_INTERVAL_SECONDS'
  
  EE_SUPERVISOR_MIN_AVAIL_PRC_KEY = 'EE_SUPERVISOR_MIN_AVAIL_PRC'

  EE_ORACLE_API_URL_KEY = 'EE_ORACLE_API_URL'
  

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


  
  
EVM_NET_DATA = {
  'mainnet': {
    EvmNetData.DAUTH_URL_KEY                    : "https://dauth.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_CONTROLLER_ADDR_KEY        : "0x90dA5FdaA92edDC80FB73114fb7FE7D97f2be017",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0xE658DF6dA3FB5d4FBa562F1D5934bd0F9c6bd423",
    EvmNetData.DAUTH_R1_ADDR_KEY                : "0x6444C6c2D527D85EA97032da9A7504d6d1448ecF",
    EvmNetData.DAUTH_MND_ADDR_KEY               : "0x0C431e546371C87354714Fcc1a13365391A549E2",
    EvmNetData.DAUTH_PROXYAPI_ADDR_KEY          : "0x0fC093d5f4B7a3fb752884397F4878f097E5Be1E",
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-mainnet.public.blastapi.io",
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-05-23 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 24,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.98,
    EvmNetData.EE_ORACLE_API_URL_KEY            : "https://oracle.ratio1.ai",
    EvmNetData.DAUTH_GET_ORACLES_ABI            : _DAUTH_ABI_GET_ORACLES,
  },

  'testnet': {
    EvmNetData.DAUTH_URL_KEY                    : "https://testnet-dauth.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_CONTROLLER_ADDR_KEY        : "0x63BEC1B3004154698830C7736107E7d3cfcbde79",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0x18E86a5829CA1F02226FA123f30d90dCd7cFd0ED",
    EvmNetData.DAUTH_R1_ADDR_KEY                : "0xCC96f389F45Fc08b4fa8e2bC4C7DA9920292ec64",
    EvmNetData.DAUTH_MND_ADDR_KEY               : "0xa8d7FFCE91a888872A9f5431B4Dd6c0c135055c1",
    EvmNetData.DAUTH_PROXYAPI_ADDR_KEY          : "0xF94b53855Fde16cbF3f9C3e300e2E6A495AE0A0A",
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-sepolia.public.blastapi.io",      
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-05-23 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 24,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.6,
    EvmNetData.EE_ORACLE_API_URL_KEY            : "https://testnet-oracle.ratio1.ai",
    EvmNetData.DAUTH_GET_ORACLES_ABI            : _DAUTH_ABI_GET_ORACLES,
  },

  
  'devnet' : {
    EvmNetData.DAUTH_URL_KEY                    : "https://devnet-dauth.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_CONTROLLER_ADDR_KEY        : "0xdd56E920810e2FD9a07C1718643E179839867253",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0x8D0CE4933728FF7C04388f0bEcC9a45676E232F7",
    EvmNetData.DAUTH_R1_ADDR_KEY                : "0x07C5678F0f4aC347496eAA8D6031b37FF3402CE5",
    EvmNetData.DAUTH_MND_ADDR_KEY               : "0x7A14Be75135a7ebdef99339CCc700C25Cda60c6E",
    EvmNetData.DAUTH_PROXYAPI_ADDR_KEY          : "0x746aaB0a8bcFB92094Acc371D7D6A2F69DaA23E3",
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-sepolia.public.blastapi.io",
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-05-23 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 1,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.6,
    EvmNetData.EE_ORACLE_API_URL_KEY            : "https://devnet-oracle.ratio1.ai",
    EvmNetData.DAUTH_GET_ORACLES_ABI            : _DAUTH_ABI_GET_ORACLES,
  },
}

class EVM_ABI_DATA:
  GET_NODE_INFO = _GET_NODE_INFO_ABI
  GET_WALLET_NODES = _GET_WALLET_NODES
  IS_NODE_ACTIVE = _DAUTH_ABI_IS_NODE_ACTIVE
  ERC20_ABI = _ERC20_ABI
  