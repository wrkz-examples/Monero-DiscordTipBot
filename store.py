from typing import List, Dict
from datetime import datetime
import time
import json
import asyncio
import aiomysql
from aiomysql.cursors import DictCursor

import rpc_client, wallet, daemonrpc_client
from config import config
import sys, traceback
import os.path

# redis
import redis

redis_pool = None
redis_conn = None
redis_expired = 120

pool = None
sys.path.append("..")

def init():
    global redis_pool
    print("PID %d: initializing redis pool..." % os.getpid())
    redis_pool = redis.ConnectionPool(host='localhost', port=6379, decode_responses=True, db=8)


def openRedis():
    global redis_pool, redis_conn
    if redis_conn is None:
        try:
            redis_conn = redis.Redis(connection_pool=redis_pool)
        except Exception as e:
            traceback.print_exc(file=sys.stdout)


async def openConnection():
    global pool
    try:
        if pool is None:
            pool = await aiomysql.create_pool(host=config.mysql.host, port=3306, minsize=5, maxsize=10, 
                                                   user=config.mysql.user, password=config.mysql.password,
                                                   db=config.mysql.db, cursorclass=DictCursor)
    except:
        print("ERROR: Unexpected error: Could not connect to MySql instance.")
        sys.exit()


async def sql_register_user(userID, coin: str, user_server: str):
    global pool
    COIN_NAME = coin.upper()
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    try:
        await openConnection()
        async with pool.acquire() as conn:
            await conn.ping(reconnect=True)
            async with conn.cursor() as cur:
                if coin_family == "XMR":
                    sql = """ SELECT * FROM xmr_user_paymentid WHERE `user_id`=%s AND `coin_name` = %s AND `user_server`=%s LIMIT 1 """
                    await cur.execute(sql, (str(userID), COIN_NAME, user_server))
                    result = await cur.fetchone()
                    if result is None:
                        balance_address = {}
                        main_address = getattr(getattr(config,"daemon"+COIN_NAME),"MainAddress")
                        if coin_family == "XMR":
                            balance_address = await wallet.make_integrated_address_xmr(main_address, COIN_NAME)
                            sql = """ INSERT INTO xmr_user_paymentid (`coin_name`, `user_id`, `main_address`, `paymentid`, 
                                      `int_address`, `paymentid_ts`, `user_server`) 
                                      VALUES (%s, %s, %s, %s, %s, %s, %s) """
                            await cur.execute(sql, (COIN_NAME, str(userID), main_address, balance_address['payment_id'], 
                                              balance_address['integrated_address'], int(time.time()), user_server))
                            await conn.commit()
                        return balance_address
                else:
                    return result
    except Exception as e:
        traceback.print_exc(file=sys.stdout)

        
async def sql_get_userwallet(userID, coin: str, user_server: str = 'DISCORD'):
    global pool
    COIN_NAME = coin.upper()
    user_server = user_server.upper()
    if user_server not in ['DISCORD', 'TELEGRAM']:
        return
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    try:
        await openConnection()
        async with pool.acquire() as conn:
            await conn.ping(reconnect=True)
            async with conn.cursor() as cur:
                if coin_family == "XMR":
                    sql = """ SELECT * FROM xmr_user_paymentid 
                              WHERE `user_id`=%s AND `coin_name` = %s AND `user_server` = %s LIMIT 1 """
                    await cur.execute(sql, (str(userID), COIN_NAME, user_server))
                    result = await cur.fetchone()
                    if result:
                        userwallet = result
                        userwallet['balance_wallet_address'] = result['int_address']
                        return userwallet
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return None


async def sql_update_user(userID, user_wallet_address, coin: str, user_server: str = 'DISCORD'):
    global pool
    COIN_NAME = coin.upper()
    user_server = user_server.upper()
    if user_server not in ['DISCORD', 'TELEGRAM']:
        return
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    try:
        await openConnection()
        async with pool.acquire() as conn:
            await conn.ping(reconnect=True)
            async with conn.cursor() as cur:
                if coin_family == "XMR":
                    sql = """ UPDATE xmr_user_paymentid SET user_wallet_address=%s WHERE `user_id`=%s AND `coin_name` = %s AND `user_server`=%s LIMIT 1 """               
                    await cur.execute(sql, (user_wallet_address, str(userID), COIN_NAME, user_server))
                    await conn.commit()
                    return user_wallet_address  # return userwallet
    except Exception as e:
        traceback.print_exc(file=sys.stdout)


async def sql_update_balances(coin: str):
    global pool
    updateTime = int(time.time())
    COIN_NAME = coin.upper()
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")

    gettopblock = None
    timeout = 12
    try:
        gettopblock = await daemonrpc_client.gettopblock(COIN_NAME, time_out=timeout)
        height = int(gettopblock['block_header']['height'])
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        
    if coin_family == "XMR":
        print('SQL: Updating get_transfers '+COIN_NAME)
        get_transfers = await wallet.get_transfers_xmr(COIN_NAME)
        if len(get_transfers) >= 1:
            # print(get_transfers)
            try:
                await openConnection()
                async with pool.acquire() as conn:
                    await conn.ping(reconnect=True)
                    async with conn.cursor() as cur:
                        sql = """ SELECT * FROM xmr_get_transfers WHERE `coin_name` = %s """
                        await cur.execute(sql, (COIN_NAME,))
                        result = await cur.fetchall()
                        d = [i['txid'] for i in result]
                        # print('=================='+COIN_NAME+'===========')
                        # print(d)
                        # print('=================='+COIN_NAME+'===========')
                        list_balance_user = {}
                        for tx in get_transfers['in']:
                            # add to balance only confirmation depth meet
                            if height > int(tx['height']) + wallet.get_confirm_depth(COIN_NAME):
                                if ('payment_id' in tx) and (tx['payment_id'] in list_balance_user):
                                    list_balance_user[tx['payment_id']] += tx['amount']
                                elif ('payment_id' in tx) and (tx['payment_id'] not in list_balance_user):
                                    list_balance_user[tx['payment_id']] = tx['amount']
                                try:
                                    if tx['txid'] not in d:
                                        sql = """ INSERT IGNORE INTO xmr_get_transfers (`coin_name`, `in_out`, `txid`, 
                                        `payment_id`, `height`, `timestamp`, `amount`, `fee`, `decimal`, `address`, time_insert) 
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) """
                                        await cur.execute(sql, (COIN_NAME, tx['type'].upper(), tx['txid'], tx['payment_id'], tx['height'], tx['timestamp'],
                                                                tx['amount'], tx['fee'], wallet.get_decimal(COIN_NAME), tx['address'], int(time.time())))
                                        await conn.commit()
                                        # add to notification list also
                                        sql = """ INSERT IGNORE INTO notify_new_tx (`coin_name`, `txid`, 
                                        `payment_id`, `height`, `amount`, `fee`, `decimal`) 
                                        VALUES (%s, %s, %s, %s, %s, %s, %s) """
                                        await cur.execute(sql, (COIN_NAME, tx['txid'], tx['payment_id'], tx['height'],
                                                                tx['amount'], tx['fee'], wallet.get_decimal(COIN_NAME)))
                                except pymysql.err.Warning as e:
                                    print(e)
                                except Exception as e:
                                    traceback.print_exc(file=sys.stdout)
                            else:
                                # add notify to redis and alert deposit. Can be clean later?
                                if config.notify_new_tx.enable_new_no_confirm == 1:
                                    key_tx_new = f'MoneroTipBot{config.discord.botuserid}:NEWTX:NOCONFIRM'
                                    key_tx_json = f'MoneroTipBot{config.discord.botuserid}:NEWTX:' + tx['txid']
                                    try:
                                        openRedis()
                                        if redis_conn and redis_conn.llen(key_tx_new) > 0:
                                            list_new_tx = redis_conn.lrange(key_tx_new, 0, -1)
                                            if list_new_tx and len(list_new_tx) > 0 and tx['txid'] not in list_new_tx:
                                                redis_conn.lpush(key_tx_new, tx['txid'])
                                                redis_conn.set(key_tx_json, json.dumps({'coin_name': COIN_NAME, 'txid': tx['txid'], 'payment_id': tx['payment_id'], 'height': tx['height'],
                                                                                    'amount': tx['amount'], 'fee': tx['fee'], 'decimal': wallet.get_decimal(COIN_NAME)}), ex=86400)
                                        elif redis_conn and redis_conn.llen(key_tx_new) == 0:
                                            redis_conn.lpush(key_tx_new, tx['txid'])
                                            redis_conn.set(key_tx_json, json.dumps({'coin_name': COIN_NAME, 'txid': tx['txid'], 'payment_id': tx['payment_id'], 'height': tx['height'],
                                                                                    'amount': tx['amount'], 'fee': tx['fee'], 'decimal': wallet.get_decimal(COIN_NAME)}), ex=86400)
                                    except Exception as e:
                                        traceback.print_exc(file=sys.stdout)
                        if len(list_balance_user) > 0:
                            list_update = []
                            timestamp = int(time.time())
                            for key, value in list_balance_user.items():
                                list_update.append((value, timestamp, key))
                            await cur.executemany(""" UPDATE xmr_user_paymentid SET `actual_balance` = %s, `lastUpdate` = %s 
                                                      WHERE paymentid = %s """, list_update)
                            await conn.commit()
            except Exception as e:
                traceback.print_exc(file=sys.stdout)


async def sql_user_balance(userID: str, coin: str, user_server: str = 'DISCORD'):
    global pool
    COIN_NAME = coin.upper()
    user_server = user_server.upper()
    if user_server not in ['DISCORD', 'TELEGRAM']:
        return
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    try:
        await openConnection()
        async with pool.acquire() as conn:
            await conn.ping(reconnect=True)
            async with conn.cursor() as cur:
                # When sending tx out, (negative)
                sql = """ SELECT SUM(amount+fee) AS SendingOut FROM xmr_external_tx 
                          WHERE `user_id`=%s AND `coin_name` = %s AND `user_server`=%s """
                await cur.execute(sql, (userID, COIN_NAME, user_server))
                result = await cur.fetchone()
                if result:
                    SendingOut = result['SendingOut']
                else:
                    SendingOut = 0

                sql = """ SELECT SUM(amount) AS Expense FROM xmr_mv_tx WHERE `from_userid`=%s AND `coin_name` = %s """
                await cur.execute(sql, (userID, COIN_NAME))
                result = await cur.fetchone()
                if result:
                    Expense = result['Expense']
                else:
                    Expense = 0

                sql = """ SELECT SUM(amount) AS Income FROM xmr_mv_tx WHERE `to_userid`=%s AND `coin_name` = %s """
                await cur.execute(sql, (userID, COIN_NAME))
                result = await cur.fetchone()
                if result:
                    Income = result['Income']
                else:
                    Income = 0

            balance = {}
            balance['Adjust'] = 0
            
            balance['Expense'] = float(Expense) if Expense else 0
            balance['Income'] = float(Income) if Income else 0
            balance['SendingOut'] = float(SendingOut) if SendingOut else 0
            balance['Adjust'] = balance['Income'] - balance['SendingOut'] - balance['Expense']
            #print(COIN_NAME)
            #print(balance)
            return balance
    except Exception as e:
        traceback.print_exc(file=sys.stdout)


# XMR Based
async def sql_mv_xmr_single(user_from: str, to_user: str, amount: float, coin: str, tiptype: str):
    global pool
    COIN_NAME = coin.upper()
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    if coin_family != "XMR":
        return False
    if tiptype.upper() not in ["TIP", "DONATE", "FAUCET", "FREETIP", "FREETIPS"]:
        return False
    try:
        await openConnection()
        async with pool.acquire() as conn:
            await conn.ping(reconnect=True)
            async with conn.cursor() as cur:
                sql = """ INSERT INTO xmr_mv_tx (`coin_name`, `from_userid`, `to_userid`, `amount`, `decimal`, `type`, `date`) 
                          VALUES (%s, %s, %s, %s, %s, %s, %s) """
                await cur.execute(sql, (COIN_NAME, user_from, to_user, amount, wallet.get_decimal(COIN_NAME), tiptype.upper(), int(time.time()),))
                await conn.commit()
                return True
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return False


async def sql_mv_xmr_multiple(user_from: str, user_tos, amount_each: float, coin: str, tiptype: str):
    # user_tos is array "account1", "account2", ....
    global pool
    COIN_NAME = coin.upper()
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    if coin_family != "XMR":
        return False
    if tiptype.upper() not in ["TIPS", "TIPALL", "FREETIP", "FREETIPS"]:
        return False
    values_str = []
    currentTs = int(time.time())
    for item in user_tos:
        values_str.append(f"('{COIN_NAME}', '{user_from}', '{item}', {amount_each}, {wallet.get_decimal(COIN_NAME)}, '{tiptype.upper()}', {currentTs})\n")
    values_sql = "VALUES " + ",".join(values_str)
    try:
        await openConnection()
        async with pool.acquire() as conn:
            await conn.ping(reconnect=True)
            async with conn.cursor() as cur:
                sql = """ INSERT INTO xmr_mv_tx (`coin_name`, `from_userid`, `to_userid`, `amount`, `decimal`, `type`, `date`) 
                          """+values_sql+""" """
                await cur.execute(sql,)
                await conn.commit()
                return True
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return False


async def sql_external_cn_xmr_single(user_server: str, user_from: str, amount: float, to_address: str, coin: str, paymentid: str = None):
    global pool
    COIN_NAME = coin.upper()
    user_server = user_server.upper()
    if user_server not in ['DISCORD', 'TELEGRAM']:
        return
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    try:
        await openConnection()
        tx_hash = None
        if coin_family == "XMR":
            tx_hash = await wallet.send_transaction('MoneroTipBot', to_address, 
                                                    amount, COIN_NAME, 0)
            if tx_hash:
                async with pool.acquire() as conn:
                    await conn.ping(reconnect=True)
                    async with conn.cursor() as cur:
                        sql = """ INSERT INTO xmr_external_tx (`coin_name`, `user_id`, `amount`, `fee`, `decimal`, `to_address`, 
                                  `date`, `tx_hash`, `tx_key`, `user_server`) 
                                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) """
                        await cur.execute(sql, (COIN_NAME, user_from, amount, tx_hash['fee'], wallet.get_decimal(COIN_NAME), to_address, \
                        int(time.time()), tx_hash['tx_hash'], tx_hash['tx_key'], user_server))
                        await conn.commit()
                return tx_hash
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return False


async def sql_get_userwallet_by_paymentid(paymentid: str, coin: str, user_server: str = 'DISCORD'):
    global pool
    user_server = user_server.upper()
    if user_server not in ['DISCORD', 'TELEGRAM']:
        return
    COIN_NAME = coin.upper()
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    try:
        await openConnection()
        async with pool.acquire() as conn:
            await conn.ping(reconnect=True)
            async with conn.cursor() as cur:
                if coin_family == "XMR":
                    sql = """ SELECT * FROM xmr_user_paymentid 
                              WHERE `paymentid`=%s AND `coin_name` = %s AND `user_server`=%s LIMIT 1 """
                    await cur.execute(sql, (paymentid, COIN_NAME, user_server))
                    result = await cur.fetchone()
                return result
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return None


async def sql_get_new_tx_table(notified: str = 'NO', failed_notify: str = 'NO'):
    global pool
    try:
        await openConnection()
        async with pool.acquire() as conn:
            await conn.ping(reconnect=True)
            async with conn.cursor() as cur:
                sql = """ SELECT * FROM notify_new_tx WHERE `notified`=%s AND `failed_notify`=%s """
                await cur.execute(sql, (notified, failed_notify,))
                result = await cur.fetchall()
                return result
    except Exception as e:
        traceback.print_exc(file=sys.stdout)


async def sql_update_notify_tx_table(payment_id: str, owner_id: str, owner_name: str, notified: str = 'YES', failed_notify: str = 'NO'):
    global pool
    try:
        await openConnection()
        async with pool.acquire() as conn:
            await conn.ping(reconnect=True)
            async with conn.cursor() as cur:
                sql = """ UPDATE notify_new_tx SET `owner_id`=%s, `owner_name`=%s, `notified`=%s, `failed_notify`=%s, 
                          `notified_time`=%s WHERE `payment_id`=%s """
                await cur.execute(sql, (owner_id, owner_name, notified, failed_notify, float("%.3f" % time.time()), payment_id,))
                await conn.commit()
                return True
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return False

