class EvmNetData:
  DAUTH_URL_KEY = 'EE_DAUTH_URL'
  DAUTH_ND_ADDR_KEY = 'EE_DAUTH_ND_ADDR'
  DAUTH_RPC_KEY = 'EE_DAUTH_RPC'
  
  EE_GENESIS_EPOCH_DATE_KEY = 'EE_GENESIS_EPOCH_DATE'
  EE_EPOCH_INTERVALS_KEY = 'EE_EPOCH_INTERVALS'
  EE_EPOCH_INTERVAL_SECONDS_KEY = 'EE_EPOCH_INTERVAL_SECONDS'
  
  EE_SUPERVISOR_MIN_AVAIL_PRC_KEY = 'EE_SUPERVISOR_MIN_AVAIL_PRC'
  
  
EVM_NET_DATA = {
  'mainnet': {
    EvmNetData.DAUTH_URL_KEY                    : "https://dauth-main.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0xE20198EE2B76eED916A568a47cdea9681f7c79BF",
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-mainnet.public.blastapi.io",
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-02-05 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 24,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.98,
  },        

  'testnet': {
    EvmNetData.DAUTH_URL_KEY                    : "https://dauth-test.ratio1.ai/get_auth_data",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0xE20198EE2B76eED916A568a47cdea9681f7c79BF",
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-sepolia.public.blastapi.io",      
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-02-05 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 24,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.6,
  },

  
  'devnet' : {
    EvmNetData.DAUTH_URL_KEY                    : "https://dauth-devnet.ratio1.ngrok.app/get_auth_data",
    EvmNetData.DAUTH_ND_ADDR_KEY                : "0x9f49fc29366F1C8285d42e7E82cA0bb668B32CeA",
    EvmNetData.DAUTH_RPC_KEY                    : "https://base-sepolia.public.blastapi.io",
    EvmNetData.EE_GENESIS_EPOCH_DATE_KEY        : "2025-01-12 16:00:00",
    EvmNetData.EE_EPOCH_INTERVALS_KEY           : 1,
    EvmNetData.EE_EPOCH_INTERVAL_SECONDS_KEY    : 3600,
    EvmNetData.EE_SUPERVISOR_MIN_AVAIL_PRC_KEY  : 0.6,
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