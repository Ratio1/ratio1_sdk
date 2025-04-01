class EvmNetData:
  DAUTH_URL_KEY = 'EE_DAUTH_URL'
  DAUTH_ND_ADDR_KEY = 'EE_DAUTH_ND_ADDR'
  DAUTH_RPC_KEY = 'EE_DAUTH_RPC'
  DAUTH_R1_ADDR_KEY = 'EE_DAUTH_R1_ADDR'
  DAUTH_MND_ADDR_KEY = 'EE_DAUTH_MND_ADDR'
  DAUTH_PROXYAPI_ADDR_KEY = 'EE_DAUTH_PROXYAPI_ADDR'
  
  EE_GENESIS_EPOCH_DATE_KEY = 'EE_GENESIS_EPOCH_DATE'
  EE_EPOCH_INTERVALS_KEY = 'EE_EPOCH_INTERVALS'
  EE_EPOCH_INTERVAL_SECONDS_KEY = 'EE_EPOCH_INTERVAL_SECONDS'
  
  EE_SUPERVISOR_MIN_AVAIL_PRC_KEY = 'EE_SUPERVISOR_MIN_AVAIL_PRC'

  EE_ORACLE_API_URL_KEY = 'EE_ORACLE_API_URL'
  
EVM_NET_DATA = {
  'mainnet': {
    EvmNetData.DAUTH_URL_KEY                    : "https://dauth.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0xE20198EE2B76eED916A568a47cdea9681f7c79BF",
    EvmNetData.DAUTH_R1_ADDR_KEY                : "0xc992DcaB6D3F8783fBf0c935E7bCeB20aa50A6f1",
    EvmNetData.DAUTH_MND_ADDR_KEY               : "0xfD52a7958088dF734D523d618e583e4d53cD7420",
    EvmNetData.DAUTH_PROXYAPI_ADDR_KEY          : "0xd9a9B7fd2De5fFAF50695d2f489a56771CA28123",
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-mainnet.public.blastapi.io",
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-02-05 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 24,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.98,
    EvmNetData.EE_ORACLE_API_URL_KEY            : "https://oracle.ratio1.ai",
  },        

  'testnet': {
    EvmNetData.DAUTH_URL_KEY                    : "https://testnet-dauth.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0xE20198EE2B76eED916A568a47cdea9681f7c79BF",
    EvmNetData.DAUTH_R1_ADDR_KEY                : "0xc992DcaB6D3F8783fBf0c935E7bCeB20aa50A6f1",
    EvmNetData.DAUTH_MND_ADDR_KEY               : "0xfD52a7958088dF734D523d618e583e4d53cD7420",
    EvmNetData.DAUTH_PROXYAPI_ADDR_KEY          : "0xF1a0b007C0155060B49D663230203B190Fe88229",    
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-sepolia.public.blastapi.io",      
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-02-05 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 24,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.6,
    EvmNetData.EE_ORACLE_API_URL_KEY             : "https://testnet-oracle.ratio1.ai",
  },

  
  'devnet' : {
    EvmNetData.DAUTH_URL_KEY                    : "https://devnet-dauth.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0x9f49fc29366F1C8285d42e7E82cA0bb668B32CeA",
    EvmNetData.DAUTH_R1_ADDR_KEY                : "0xEF38a3d84D3E3111fb7b794Ba3240187b8B32825", 
    EvmNetData.DAUTH_MND_ADDR_KEY               : "0x909d33Ab74d5A85F1fc963ae63af7B97eAe76f40",
    EvmNetData.DAUTH_PROXYAPI_ADDR_KEY          : "0x9228545b7BCa69A46A2eD4D5B23e6159B986Cf62",    
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-sepolia.public.blastapi.io",
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-02-12 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 1,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.6,
    EvmNetData.EE_ORACLE_API_URL_KEY            : "https://devnet-oracle.ratio1.ai",
  },

}


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

_DAUTH_ABI_GET_SIGNERS = [{
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