from typing import List, Dict
import json
from uuid import uuid4
import rpc_client
import aiohttp
import asyncio
import time
## For random paymentid
import secrets, sha3

from config import config

import sys
sys.path.append("..")


async def send_transaction(from_address: str, to_address: str, amount: int, coin: str, acc_index: int = None) -> str:
    COIN_NAME = coin.upper()
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    result = None
    time_out = 64
    if coin_family == "XMR":
        payload = {
            "destinations": [{'amount': amount, 'address': to_address}],
            "account_index": acc_index,
            "subaddr_indices": [],
            "priority": 1,
            "unlock_time": 0,
            "get_tx_key": True,
            "get_tx_hex": False,
            "get_tx_metadata": False
        }
        result = await rpc_client.call_aiohttp_wallet('transfer', COIN_NAME, time_out=time_out, payload=payload)
        if result:
            if ('tx_hash' in result) and ('tx_key' in result):
                return result
    return result


async def get_tx_fee_xmr(coin: str, amount: int = None, to_address: str = None):
    COIN_NAME = coin.upper()
    timeout = 32
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")      
    if coin_family == "XMR":
        payload = {
            "destinations": [{'amount': amount, 'address': to_address}],
            "account_index": 0,
            "subaddr_indices": [],
            "get_tx_key": True,
            "do_not_relay": True,
            "get_tx_hex": True,
            "get_tx_metadata": False
        }
        result = await rpc_client.call_aiohttp_wallet('transfer', COIN_NAME, time_out=timeout, payload=payload)
        if result and ('tx_hash' in result) and ('tx_key' in result) and ('fee' in result): return result['fee']


async def rpc_cn_wallet_save(coin: str):
    COIN_NAME = coin.upper()
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    start = time.time()
    if coin_family == "XMR":
        result = await rpc_client.call_aiohttp_wallet('store', coin)
    end = time.time()
    return float(end - start)


async def validate_address_xmr(address: str, coin: str):
    coin_family = getattr(getattr(config,"daemon"+coin),"coin_family","XMR")
    if coin_family == "XMR":
        payload = {
            "address" : address,
            "any_net_type": True,
            "allow_openalias": True
        }
        address_xmr = await rpc_client.call_aiohttp_wallet('validate_address', coin, payload=payload)
        if address_xmr:
            return address_xmr
        else:
            return None


## make random paymentid:
def paymentid_gen(length=None):
    if length is None:
        length=32
    return secrets.token_hex(length) 


async def make_integrated_address_xmr(address: str, coin: str, paymentid: str = None):
    COIN_NAME = coin.upper()
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    if paymentid:
        try:
            value = int(paymentid, 16)
        except ValueError:
            return False
    else:
        paymentid = paymentid_gen(8)
    if coin_family == "XMR":
        payload = {
            "standard_address" : address,
            "payment_id": {} or paymentid
        }
        address_ia = await rpc_client.call_aiohttp_wallet('make_integrated_address', COIN_NAME, payload=payload)
        if address_ia:
            return address_ia
        else:
            return None


async def get_transfers_xmr(coin: str, height_start: int = None, height_end: int = None):
    COIN_NAME = coin.upper()
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    if coin_family == "XMR":
        payload = None
        if height_start and height_end:
            payload = {
                "in" : True,
                "out": True,
                "pending": False,
                "failed": False,
                "pool": False,
                "filter_by_height": True,
                "min_height": height_start,
                "max_height": height_end
            }
        else:
            payload = {
                "in" : True,
                "out": True,
                "pending": False,
                "failed": False,
                "pool": False,
                "filter_by_height": False
            }
        result = await rpc_client.call_aiohttp_wallet('get_transfers', COIN_NAME, payload=payload)
        return result


def get_mixin(coin: str = None):
    return getattr(config,"daemon"+coin,config.daemonXMS).mixin


def get_decimal(coin: str = None):
    return getattr(config,"daemon"+coin,config.daemonXMS).decimal


def get_addrlen(coin: str = None):
    return getattr(config,"daemon"+coin,config.daemonXMS).AddrLen


def get_intaddrlen(coin: str = None):
    return getattr(config,"daemon"+coin,config.daemonXMS).IntAddrLen


def get_min_tx_amount(coin: str):
    return getattr(config,"daemon"+coin,config.daemonXMS).min_tx_amount


def get_max_tx_amount(coin: str):
    return getattr(config,"daemon"+coin,config.daemonXMS).max_tx_amount


def get_confirm_depth(coin: str):
    return int(getattr(config,"daemon"+coin,config.daemonXMS).confirm_depth)


def get_main_address(coin: str):
    return getattr(config,"daemon"+coin,config.daemonXMS).MainAddress


def get_diff_target(coin: str = None):
    return getattr(config,"daemon"+coin,config.daemonXMS).DiffTarget

