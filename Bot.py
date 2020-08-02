import discord
from discord.ext import commands
from discord.ext.commands import Bot, AutoShardedBot, when_mentioned_or, CheckFailure
from discord.utils import get

import os
import time, timeago
from datetime import datetime
from config import config
import click
import sys, traceback
import asyncio, aiohttp

import re
import math, random

import store, daemonrpc_client
from wallet import *
from generic_xmr.address_xmr import address_xmr as address_xmr

from typing import List, Dict

# for randomString
import random, string

# redis
import redis

# Coin using wallet-api
ENABLE_XMR = config.Enable_Coin_XMR.split(",")
TX_IN_PROCESS = []

EMOJI_ERROR = "\u274C"
EMOJI_OK_BOX = "\U0001F197"
EMOJI_RED_NO = "\u26D4"
EMOJI_OK_HAND = "\U0001F44C"
EMOJI_MONEYBAG = "\U0001F4B0"
EMOJI_QUESTEXCLAIM = "\u2049"
EMOJI_ARROW_RIGHTHOOK = "\u21AA"
EMOJI_ZIPPED_MOUTH = "\U0001F910"
EMOJI_MONEYFACE = "\U0001F911"

bot_help_about = "About MoneroTestTipBot."
bot_help_invite = "Invite link of bot to your server."
bot_help_balance = "Check your tipbot balance."
bot_help_deposit = "Get your wallet ticker's deposit address."
bot_help_register = "Register or change your deposit address for MoneroTestTipBot."
bot_help_withdraw = "Withdraw coin from your MoneroTestTipBot balance."


bot_help_admin_shutdown = "Restart bot."
bot_help_admin_maintenance = "Bot to be in maintenance mode ON / OFF"



redis_pool = None
redis_conn = None
redis_expired = 120


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


# Steal from https://github.com/cree-py/RemixBot/blob/master/bot.py#L49
async def get_prefix(bot, message):
    """Gets the prefix for the guild"""
    pre_cmd = config.discord.prefixCmd
    if isinstance(message.channel, discord.DMChannel):
        pre_cmd = config.discord.prefixCmd
        extras = [pre_cmd, 'xms.', 'xms!', '.']
        return when_mentioned_or(*extras)(bot, message)

    extras = [pre_cmd, 'xms.', 'xms!', '.']
    return when_mentioned_or(*extras)(bot, message)

bot = AutoShardedBot(command_prefix=get_prefix, owner_id = config.discord.ownerID, case_insensitive=True)


@bot.event
async def on_shard_ready(shard_id):
    print(f'Shard {shard_id} connected')

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    game = discord.Game(name=".")
    await bot.change_presence(status=discord.Status.online, activity=game)


@bot.event
async def on_message(message):
    # Do not remove this, otherwise, command not working.
    ctx = await bot.get_context(message)
    await bot.invoke(ctx)


@bot.event
async def on_reaction_add(reaction, user):
    # If bot re-act, ignore.
    if user.id == bot.user.id:
        return
    # If other people beside bot react.
    else:
        # If re-action is OK box and message author is bot itself
        if reaction.emoji == EMOJI_OK_BOX and reaction.message.author.id == bot.user.id:
            await reaction.message.delete()


@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id is None:
        return  # Reaction is on a private message
    """Handle a reaction add."""
    try:
        emoji_partial = str(payload.emoji)
        message_id = payload.message_id
        channel_id = payload.channel_id
        user_id = payload.user_id
        guild = bot.get_guild(payload.guild_id)
        channel = bot.get_channel(id=channel_id)
        if not channel:
            return
        if isinstance(channel, discord.DMChannel):
            return
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        return
    message = None
    author = None
    if message_id:
        try:
            message = await channel.fetch_message(message_id)
            author = message.author
        except (discord.errors.NotFound, discord.errors.Forbidden) as e:
            # No message found
            return
        member = bot.get_user(id=user_id)
        if emoji_partial in [EMOJI_OK_BOX] and message.author.id == bot.user.id \
            and author != member and message:
            # Delete message
            try:
                await message.delete()
                return
            except discord.errors.NotFound as e:
                # No message found
                return



@bot.command(pass_context=True, name='about', help=bot_help_about)
async def about(ctx):
    invite_link = "https://discordapp.com/oauth2/authorize?client_id="+str(bot.user.id)+"&scope=bot"
    botdetails = discord.Embed(title='About Me', description='This bot\'s wallet is running with XMR stagenet', timestamp=datetime.utcnow(), colour=7047495)
    botdetails.add_field(name='Invite Me:', value=f'[Invite TipBot]({invite_link})', inline=True)
    botdetails.add_field(name='Servers I am in:', value=len(bot.guilds), inline=True)
    botdetails.add_field(name='XMR Stagenet', value="[Explorer](https://community.xmr.to/explorer/stagenet) / [Faucet](https://community.xmr.to/faucet/stagenet)", inline=False)
    botdetails.set_footer(text='Made in Python3.8 with discord.py library!', icon_url='http://findicons.com/files/icons/2804/plex/512/python.png')
    botdetails.set_author(name=bot.user.name, icon_url=bot.user.avatar_url)
    try:
        await ctx.send(embed=botdetails)
    except Exception as e:
        await ctx.send(embed=botdetails)
        traceback.print_exc(file=sys.stdout)


@bot.command(pass_context=True, name='invite', aliases=['inviteme'], help=bot_help_invite)
async def invite(ctx):
    invite_link = "https://discordapp.com/oauth2/authorize?client_id="+str(bot.user.id)+"&scope=bot"
    await ctx.send('**[INVITE LINK]**\n\n'
                f'{invite_link}')



@bot.command(pass_context=True, aliases=['stat'], help='Get Coin Stats')
async def stats(ctx):
    COIN_NAME = "XMS"
    gettopblock = None
    timeout = 30
    try:
        gettopblock = await daemonrpc_client.gettopblock(COIN_NAME, time_out=timeout)
    except asyncio.TimeoutError:
        msg = await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} {COIN_NAME} connection to daemon timeout after {str(timeout)} seconds. I am checking info from wallet now.')
        await msg.add_reaction(EMOJI_OK_BOX)
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    if gettopblock:
        try:
            COIN_DEC = get_decimal(COIN_NAME)
            COIN_DIFF = get_diff_target(COIN_NAME)
            blockfound = datetime.utcfromtimestamp(int(gettopblock['block_header']['timestamp'])).strftime("%Y-%m-%d %H:%M:%S")
            ago = str(timeago.format(blockfound, datetime.utcnow()))
            difficulty = "{:,}".format(gettopblock['block_header']['difficulty'])
            hashrate = str(hhashes(int(gettopblock['block_header']['difficulty']) / int(COIN_DIFF)))
            height = "{:,}".format(gettopblock['block_header']['height'])
            reward = "{:,}".format(int(gettopblock['block_header']['reward'])/int(COIN_DEC))
            if coin_family == "XMR":
                desc = f"`{num_format_coin(get_min_tx_amount(COIN_NAME), COIN_NAME)}-{num_format_coin(get_max_tx_amount(COIN_NAME), COIN_NAME)}{COIN_NAME}`"
                embed = discord.Embed(title=f"[ {COIN_NAME} ]", 
                                      description='This bot\'s wallet is running with XMR stagenet', 
                                      timestamp=datetime.utcnow(), color=0xDEADBF)
                embed.set_author(name=bot.user.name, icon_url=bot.user.avatar_url)
                embed.add_field(name="NET HEIGHT", value=str(height), inline=True)
                embed.add_field(name="FOUND", value=ago, inline=True)
                embed.add_field(name="DIFFICULTY", value=difficulty, inline=True)
                embed.add_field(name="BLOCK REWARD", value=f'{reward}{COIN_NAME}', inline=True)
                embed.add_field(name="NETWORK HASH", value=hashrate, inline=True)
                embed.add_field(name="Tx Min/Max", value=desc, inline=True)
                try:
                    walletStatus = await daemonrpc_client.getWalletStatus(COIN_NAME)
                    if walletStatus:
                        t_percent = '{:,.2f}'.format(truncate((walletStatus['height'] - 1)/gettopblock['block_header']['height']*100,2))
                        embed.add_field(name="WALLET SYNC %", value=t_percent + '% (' + '{:,.0f}'.format(walletStatus['height'] - 1) + ')', inline=True)
                except Exception as e:
                    traceback.print_exc(file=sys.stdout)
                embed.add_field(name='XMR Stagenet', value="[Explorer](https://community.xmr.to/explorer/stagenet) / [Faucet](https://community.xmr.to/faucet/stagenet)", inline=True)
                embed.set_footer(text='MoneroTipBot')
                try:
                    msg = await ctx.send(embed=embed)
                    await msg.add_reaction(EMOJI_OK_BOX)
                except (discord.Forbidden, discord.errors.Forbidden) as e:
                    # if embedded denied
                    msg = await ctx.send(f'**[ {COIN_NAME} ]**\n'
                                   f'```[NETWORK HEIGHT] {height}\n'
                                   f'[TIME]           {ago}\n'
                                   f'[DIFFICULTY]     {difficulty}\n'
                                   f'[BLOCK REWARD]   {reward}{COIN_NAME}\n'
                                   f'[TX Min/Max]     {num_format_coin(get_min_tx_amount(COIN_NAME), COIN_NAME)}-{num_format_coin(get_max_tx_amount(COIN_NAME), COIN_NAME)}{COIN_NAME}\n'
                                   '```')
                    await msg.add_reaction(EMOJI_OK_BOX)
                return
        except Exception as e:
            traceback.print_exc(file=sys.stdout)



@bot.command(pass_context=True, help='Tip other people')
async def tip(ctx, amount: str, *args):
    global TX_IN_PROCESS
    amount = amount.replace(",", "")
    COIN_NAME = "XMS"
    try:
        amount = float(amount)
    except ValueError:
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Invalid amount.')
        return

    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send(f'{EMOJI_RED_NO} This command can not be in private.')
        return

    if len(ctx.message.mentions) == 1 and (bot.user in ctx.message.mentions):
        # Tip to TipBot
        member = ctx.message.mentions[0]
        print('TipBot is receiving tip from {} amount: {}{}'.format(ctx.message.author.name, amount, COIN_NAME))
    elif len(ctx.message.mentions) == 1 and (bot.user not in ctx.message.mentions):
        member = ctx.message.mentions[0]
        if ctx.message.author.id == member.id:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Tip me if you want.')
            return
        pass
    elif len(ctx.message.mentions) > 1:
        await _tip(ctx, amount, COIN_NAME)
        return

    COIN_NAME = "XMS"
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")
    if coin_family == "XMR":
        COIN_DEC = get_decimal(COIN_NAME)
        real_amount = int(amount * COIN_DEC)
        MinTx = get_min_tx_amount(COIN_NAME)
        MaxTX = get_max_tx_amount(COIN_NAME)
        user_from = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME)
        if user_from is None:
            user_from = await store.sql_register_user(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
            user_from = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME)
        userdata_balance = await store.sql_user_balance(str(ctx.message.author.id), COIN_NAME)
        if real_amount < MinTx:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Transactions cannot be smaller than '
                           f'{num_format_coin(MinTx, COIN_NAME)} '
                           f'{COIN_NAME}.')
            return
        elif real_amount > MaxTX:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Transactions cannot be bigger than '
                           f'{num_format_coin(MaxTX, COIN_NAME)} '
                           f'{COIN_NAME}.')
            return
        elif real_amount > float(user_from['actual_balance']) + float(userdata_balance['Adjust']):
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Insufficient balance to send tip of '
                            f'{num_format_coin(real_amount, COIN_NAME)} '
                            f'{COIN_NAME} to {member.name}#{member.discriminator}.')
            return
        if ctx.message.author.id not in TX_IN_PROCESS:
            TX_IN_PROCESS.append(ctx.message.author.id)
            try:
                tip = await store.sql_mv_xmr_single(str(ctx.message.author.id), str(member.id), real_amount, COIN_NAME, "TIP")
            except Exception as e:
                traceback.print_exc(file=sys.stdout)
            TX_IN_PROCESS.remove(ctx.message.author.id)
        else:
            # reject and tell to wait
            msg = await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} You have another tx in process. Please wait it to finish. ')
            await msg.add_reaction(EMOJI_OK_BOX)
            return
        if tip:
            try:
                await ctx.message.author.send(
                    f'{EMOJI_ARROW_RIGHTHOOK} Tip of {num_format_coin(real_amount, COIN_NAME)} '
                    f'{COIN_NAME} '
                    f'was sent to {member.name}#{member.discriminator} in server `{ctx.guild.name}`\n')
            except (discord.Forbidden, discord.errors.Forbidden) as e:
                pass
                # await store.sql_toggle_tipnotify(str(ctx.message.author.id), "OFF")
            try:
                await ctx.send(
                    f'{EMOJI_MONEYFACE} {member.mention} got a tip of {num_format_coin(real_amount, COIN_NAME)} '
                    f'{COIN_NAME} from {ctx.message.author.name}#{ctx.message.author.discriminator}')
            except (discord.Forbidden, discord.errors.Forbidden) as e:
                try:
                    await member.send(f'{EMOJI_MONEYFACE} You got a tip of {num_format_coin(real_amount, COIN_NAME)} '
                                      f'{COIN_NAME} from {ctx.message.author.name}#{ctx.message.author.discriminator} in server `{ctx.guild.name}`\n')
                except (discord.Forbidden, discord.errors.Forbidden) as e:
                    await ctx.message.add_reaction(EMOJI_ZIPPED_MOUTH)
                    pass
                # await store.sql_toggle_tipnotify(str(member.id), "OFF")
            await ctx.message.add_reaction(EMOJI_OK_HAND)
            return
        else:
            await ctx.message.add_reaction(EMOJI_ERROR)
        return


@bot.command(pass_context=True, help='Tip all online user')
async def tipall(ctx, amount: str, user: str='ONLINE'):
    global TX_IN_PROCESS
    COIN_NAME = "XMS"

    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send(f'{EMOJI_RED_NO} This command can not be in private.')
        return

    amount = amount.replace(",", "")
    try:
        amount = float(amount)
    except ValueError:
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Invalid amount.')
        return

    print('TIPALL COIN_NAME:' + COIN_NAME)
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","XMR")

    if coin_family == "XMR":
        COIN_DEC = get_decimal(COIN_NAME)
        real_amount = int(amount * COIN_DEC)
        MinTx = get_min_tx_amount(COIN_NAME)
        MaxTX = get_max_tx_amount(COIN_NAME)
        user_from = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME)
        if user_from is None:
            user_from = await store.sql_register_user(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
            user_from = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME)
        userdata_balance = await store.sql_user_balance(str(ctx.message.author.id), COIN_NAME)
        if real_amount < MinTx:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Transactions cannot be smaller than '
                           f'{num_format_coin(MinTx, COIN_NAME)} '
                           f'{COIN_NAME}.')
            return
        elif real_amount > MaxTX:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Transactions cannot be bigger than '
                           f'{num_format_coin(MaxTX, COIN_NAME)} '
                           f'{COIN_NAME}.')
            return
        elif real_amount > float(user_from['actual_balance']) + float(userdata_balance['Adjust']):
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Insufficient balance to send tip of '
                            f'{num_format_coin(real_amount, COIN_NAME)} '
                            f'{COIN_NAME}.')
            return
        listMembers = [member for member in ctx.guild.members if member.status != discord.Status.offline and member.bot == False]
        if user.upper() == "ANY":
            listMembers = [member for member in ctx.guild.members]
        if len(listMembers) <= 1:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} There is no number of users.')
            return
        print("Number of tip-all in {}: {}".format(ctx.guild.name, len(listMembers)))
        memids = []  # list of member ID
        for member in listMembers:
            # print(member.name) # you'll just print out Member objects your way.
            if ctx.message.author.id != member.id:
                memids.append(str(member.id))
        amountDiv = round(real_amount / len(memids), 4)
        if (real_amount / len(memids)) < MinTx:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Transactions cannot be smaller than '
                           f'{num_format_coin(MinTx, COIN_NAME)} '
                           f'{COIN_NAME} for each member. You need at least {num_format_coin(len(memids) * MinTx, COIN_NAME)}{COIN_NAME}.')
            return
        if ctx.message.author.id not in TX_IN_PROCESS:
            TX_IN_PROCESS.append(ctx.message.author.id)
            try:
                tips = await store.sql_mv_xmr_multiple(str(ctx.message.author.id), memids, amountDiv, COIN_NAME, "TIPALL")
            except Exception as e:
                traceback.print_exc(file=sys.stdout)
            TX_IN_PROCESS.remove(ctx.message.author.id)
        else:
            msg = await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} You have another tx in process. Please wait it to finish. ')
            await msg.add_reaction(EMOJI_OK_BOX)
            return
        if tips:
            tipAmount = num_format_coin(real_amount, COIN_NAME)
            ActualSpend_str = num_format_coin(amountDiv * len(memids), COIN_NAME)
            amountDiv_str = num_format_coin(amountDiv, COIN_NAME)
            numMsg = 0
            for member in listMembers:
                dm_user = True
                if ctx.message.author.id != member.id and member.id != bot.user.id:
                    try:
                        if dm_user:
                            try:
                                await member.send(f'{EMOJI_MONEYFACE} You got a tip of {amountDiv_str} '
                                                  f'{COIN_NAME} from {ctx.message.author.name}#{ctx.message.author.discriminator} `{config.discord.prefixCmd}tipall` in server `{ctx.guild.name}`\n')
                                numMsg += 1
                            except (discord.Forbidden, discord.errors.Forbidden) as e:
                                # await store.sql_toggle_tipnotify(str(member.id), "OFF")
                                pass
                    except Exception as e:
                        traceback.print_exc(file=sys.stdout)
            # tipper shall always get DM. Ignore notifyList
            try:
                await ctx.message.author.send(
                    f'{EMOJI_ARROW_RIGHTHOOK} Tip of {tipAmount} '
                    f'{COIN_NAME} '
                    f'was sent spread to ({len(memids)}) members in server `{ctx.guild.name}`.\n'
                    f'Each member got: `{amountDiv_str}{COIN_NAME}`\n'
                    f'Actual spending: `{ActualSpend_str}{COIN_NAME}`')
            except (discord.Forbidden, discord.errors.Forbidden) as e:
                pass
                # await store.sql_toggle_tipnotify(str(ctx.message.author.id), "OFF")
            await ctx.message.add_reaction(EMOJI_OK_HAND)
        else:
            await ctx.message.add_reaction(EMOJI_ERROR)
        return



@bot.command(pass_context=True, name='balance', aliases=['bal'], help=bot_help_balance)
async def balance(ctx):
    global TX_IN_PROCESS
    COIN_NAME = "XMS"
    wallet = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
    if wallet is None:
        userregister = await store.sql_register_user(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
        wallet = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
    if wallet:
        note = ''
        if ctx.message.author.id in TX_IN_PROCESS:
            note = '*You have some a tx in progress. Balance is being updated.*'
        userdata_balance = await store.sql_user_balance(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
        balance_actual = num_format_coin(wallet['actual_balance'] + float(userdata_balance['Adjust']), COIN_NAME)
        await ctx.message.add_reaction(EMOJI_OK_HAND)
        msg = await ctx.send(f'**[ YOUR BALANCE ]**\n```{balance_actual}{COIN_NAME}```{note}')
        await msg.add_reaction(EMOJI_OK_BOX)
        return


@bot.command(pass_context=True, name='deposit', help=bot_help_deposit)
async def deposit(ctx):
    COIN_NAME = "XMS"
    wallet = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
    if wallet is None:
        userregister = await store.sql_register_user(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
        wallet = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
    if wallet is None:
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Internal Error')
        return
    embed = discord.Embed(title=f'Deposit for {ctx.author.name}#{ctx.author.discriminator}', description='This bot\'s wallet is running with XMR stagenet', timestamp=datetime.utcnow(), colour=7047495)
    embed.set_author(name=bot.user.name, icon_url=bot.user.avatar_url)
    if wallet['balance_wallet_address']:
        await ctx.message.add_reaction(EMOJI_OK_HAND)
        embed.add_field(name="Deposit Address", value="`{}`".format(wallet['balance_wallet_address']), inline=False)
        if 'user_wallet_address' in wallet and wallet['user_wallet_address'] and isinstance(ctx.channel, discord.DMChannel) == True:
            embed.add_field(name="Withdraw Address", value="`{}`".format(wallet['user_wallet_address']), inline=False)
        elif 'user_wallet_address' in wallet and wallet['user_wallet_address'] and isinstance(ctx.channel, discord.DMChannel) == False:
            embed.add_field(name="Withdraw Address", value="`(Only in DM)`", inline=False)
        embed.add_field(name='XMR Stagenet', value="[Explorer](https://community.xmr.to/explorer/stagenet) / [Faucet](https://community.xmr.to/faucet/stagenet)", inline=False)
        msg = await ctx.send(embed=embed)
        await msg.add_reaction(EMOJI_OK_BOX)
    else:
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Internal Error')
        await ctx.message.add_reaction(EMOJI_ERROR)
    return


@bot.command(pass_context=True, name='register', aliases=['reg'], help=bot_help_register)
async def register(ctx, wallet_address: str):
    if wallet_address.isalnum() == False:
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Invalid address:\n'
                       f'`{wallet_address}`')
        return

    COIN_NAME = get_cn_coin_from_address(wallet_address)
    if COIN_NAME:
        pass
    else:
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Unknown Ticker.')
        return

    main_address = getattr(getattr(config,"daemon"+COIN_NAME),"MainAddress")
    if wallet_address == main_address:
        await ctx.message.add_reaction(EMOJI_QUESTEXCLAIM)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} {COIN_NAME} do not register with main address. You could lose your coin when withdraw.')
        return

    user = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME)
    if user is None:
        userregister = await store.sql_register_user(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
        user = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME)

    existing_user = user

    valid_address = None
    if COIN_NAME in ["XMS"]:
        valid_address = await validate_address_xmr(str(wallet_address), COIN_NAME)
        if valid_address is None:
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Invalid address:\n'
                           f'`{wallet_address}`')
        if valid_address['valid'] == True and valid_address['integrated'] == False \
        and valid_address['subaddress'] == False and valid_address['nettype'] == 'stagenet':
            # re-value valid_address
            valid_address = str(wallet_address)
        else:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Please use {COIN_NAME} main address.')
            return
    else:
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Unknown Ticker.')
        return
    # correct print(valid_address)
    if valid_address is None:
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Invalid {COIN_NAME} address:\n'
                       f'`{wallet_address}`')
        return

    if valid_address != wallet_address:
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Invalid {COIN_NAME} address:\n'
                       f'`{wallet_address}`')
        return

    # if they want to register with tipjar address
    try:
        if user['balance_wallet_address'] == wallet_address:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} You can not register with your {COIN_NAME} tipjar\'s address.\n'
                           f'`{wallet_address}`')
            return
        else:
            pass
    except Exception as e:
        await ctx.message.add_reaction(EMOJI_ERROR)
        print('Error during register user address:' + str(e))
        return

    if 'user_wallet_address' in existing_user and existing_user['user_wallet_address']:
        prev_address = existing_user['user_wallet_address']
        if prev_address != valid_address:
            await store.sql_update_user(str(ctx.message.author.id), wallet_address, COIN_NAME)
            await ctx.message.add_reaction(EMOJI_OK_HAND)
            await ctx.send(f'Your {COIN_NAME} {ctx.author.mention} withdraw address has changed from:\n'
                           f'`{prev_address}`\n to\n '
                           f'`{wallet_address}`')
            return
        else:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{ctx.author.mention} Your {COIN_NAME} previous and new address is the same.')
            return
    else:
        await store.sql_update_user(str(ctx.message.author.id), wallet_address, COIN_NAME)
        await ctx.message.add_reaction(EMOJI_OK_HAND)
        await ctx.send(f'{ctx.author.mention} You have registered {COIN_NAME} withdraw address.\n'
                       f'You can use `{config.discord.prefixCmd}withdraw AMOUNT` anytime.')
        return


@bot.command(pass_context=True, help=bot_help_withdraw)
async def withdraw(ctx, amount: str):
    global TX_IN_PROCESS
    amount = amount.replace(",", "")
    try:
        amount = float(amount)
    except ValueError:
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Invalid given amount for command withdraw.')
        return

    COIN_NAME = "XMS"
    COIN_DEC = get_decimal(COIN_NAME)
    MinTx = get_min_tx_amount(COIN_NAME)
    MaxTX = get_max_tx_amount(COIN_NAME)
    real_amount = int(amount * COIN_DEC)

    user_from = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME)
    if user_from is None:
        user_from = await store.sql_register_user(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
        user_from = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME)

    CoinAddress = None
    if user_from['user_wallet_address'] is None:
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} You do not have a withdrawal address, please use '
                       f'`{config.discord.prefixCmd}register wallet_address` to register.')
        return
    else:
        CoinAddress = user_from['user_wallet_address']

    if COIN_NAME in ["XMS"]:
        user_from = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
        userdata_balance = await store.sql_user_balance(str(ctx.message.author.id), COIN_NAME, 'DISCORD')

        # If balance 0, no need to check anything
        if float(user_from['actual_balance']) + float(userdata_balance['Adjust']) <= 0:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Please check your **{COIN_NAME}** balance.')
            return
        if real_amount > float(user_from['actual_balance']) + float(userdata_balance['Adjust']):
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Insufficient balance to send out '
                           f'{num_format_coin(real_amount, COIN_NAME)} '
                           f'{COIN_NAME}.')
            return

        NetFee = await get_tx_fee_xmr(coin = COIN_NAME, amount = real_amount, to_address = CoinAddress)
        if NetFee is None:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Can not get fee from network for: '
                           f'{num_format_coin(real_amount, COIN_NAME)} '
                           f'{COIN_NAME}. Please try again later in a few minutes.')
            return
        if real_amount + NetFee > float(user_from['actual_balance']) + float(userdata_balance['Adjust']):
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Insufficient balance to send out '
                           f'{num_format_coin(real_amount, COIN_NAME)} '
                           f'{COIN_NAME}. You need to leave at least network fee: {num_format_coin(NetFee, COIN_NAME)}{COIN_NAME}')
            return
        if real_amount < MinTx:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Transaction cannot be smaller than '
                           f'{num_format_coin(MinTx, COIN_NAME)} '
                           f'{COIN_NAME}.')
            return
        if real_amount > MaxTX:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Transaction cannot be bigger than '
                           f'{num_format_coin(MaxTX, COIN_NAME)} '
                           f'{COIN_NAME}.')
            return

        SendTx = None
        if ctx.message.author.id not in TX_IN_PROCESS:
            TX_IN_PROCESS.append(ctx.message.author.id)
            try:
                SendTx = await store.sql_external_cn_xmr_single('DISCORD', str(ctx.message.author.id), real_amount,
                                                                CoinAddress, COIN_NAME)
            except Exception as e:
                traceback.print_exc(file=sys.stdout)
            TX_IN_PROCESS.remove(ctx.message.author.id)
        else:
            # reject and tell to wait
            msg = await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} You have another tx in process. Please wait it to finish. ')
            await msg.add_reaction(EMOJI_OK_BOX)
            return
        if SendTx:
            SendTx_hash = SendTx['tx_hash']
            await ctx.message.add_reaction(EMOJI_OK_BOX)
            await ctx.send(f'{EMOJI_ARROW_RIGHTHOOK} You have withdrawn {num_format_coin(real_amount, COIN_NAME)} '
                           f'{COIN_NAME} to `{CoinAddress}`.\n'
                           f'Transaction hash: `{SendTx_hash}`\n'
                           'Network fee deducted from your account balance.')
            return
        else:
            await ctx.message.add_reaction(EMOJI_ERROR)
            return
        return



# Multiple tip
async def _tip(ctx, amount, coin: str):
    COIN_NAME = coin.upper()
    coin_family = getattr(getattr(config,"daemon"+COIN_NAME),"coin_family","TRTL")
    if coin_family == "XMR":
        COIN_DEC = get_decimal(COIN_NAME)
        MinTx = get_min_tx_amount(COIN_NAME)
        MaxTX = get_max_tx_amount(COIN_NAME)
        user_from = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME)
        if user_from is None:
            user_from = await store.sql_register_user(str(ctx.message.author.id), COIN_NAME, 'DISCORD')
            user_from = await store.sql_get_userwallet(str(ctx.message.author.id), COIN_NAME)
        real_amount = int(round(float(amount) * COIN_DEC))
        userdata_balance = await store.sql_user_balance(str(ctx.message.author.id), COIN_NAME)
        if real_amount < MinTx:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Transactions cannot be smaller than '
                           f'{num_format_coin(MinTx, COIN_NAME)} '
                           f'{COIN_NAME}.')
            return
        elif real_amount > MaxTX:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Transactions cannot be bigger than '
                           f'{num_format_coin(MaxTX, COIN_NAME)} '
                           f'{COIN_NAME}.')
            return
        elif real_amount > user_from['actual_balance'] + userdata_balance['Adjust']:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Insufficient balance to send tip of '
                            f'{num_format_coin(real_amount, COIN_NAME)} '
                            f'{COIN_NAME}.')
            return
        listMembers = ctx.message.mentions
        memids = []  # list of member ID
        for member in listMembers:
            if ctx.message.author.id != member.id and member in ctx.guild.members:
                memids.append(str(member.id))
        TotalAmount = real_amount * len(memids)

        if TotalAmount > MaxTX:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Total transaction cannot be bigger than '
                           f'{num_format_coin(MaxTX, COIN_NAME)} '
                           f'{COIN_NAME}.')
            return
        if user_from['actual_balance'] + userdata_balance['Adjust'] < TotalAmount:
            await ctx.message.add_reaction(EMOJI_ERROR)
            await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} You don\'t have sufficient balance. ')
            return
        try:
            tips = await store.sql_mv_xmr_multiple(str(ctx.message.author.id), memids, real_amount, COIN_NAME, "TIPS")
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
        if tips:
            tipAmount = num_format_coin(TotalAmount, COIN_NAME)
            amountDiv_str = num_format_coin(real_amount, COIN_NAME)
            # tipper shall always get DM. Ignore notifyList
            try:
                await ctx.message.author.send(
                    f'{EMOJI_ARROW_RIGHTHOOK} Tip of {tipAmount} '
                    f'{COIN_NAME} '
                    f'was sent to ({len(memids)}) members in server `{ctx.guild.name}`.\n'
                    f'Each member got: `{amountDiv_str}{COIN_NAME}`\n')
            except (discord.Forbidden, discord.errors.Forbidden) as e:
                pass
                # await store.sql_toggle_tipnotify(str(ctx.message.author.id), "OFF")
            for member in ctx.message.mentions:
                # print(member.name) # you'll just print out Member objects your way.
                if ctx.message.author.id != member.id and member.id != bot.user.id:
                    try:
                        await member.send(f'{EMOJI_MONEYFACE} You got a tip of `{amountDiv_str}{COIN_NAME}` '
                                          f'from {ctx.message.author.name}#{ctx.message.author.discriminator} in server `{ctx.guild.name}`\n')
                    except (discord.Forbidden, discord.errors.Forbidden) as e:
                        # await store.sql_toggle_tipnotify(str(member.id), "OFF")
                        pass
            await ctx.message.add_reaction(EMOJI_OK_HAND)
            return
        else:
            await ctx.message.add_reaction(EMOJI_ERROR)
            return
        return


# Let's run balance update by a separate process
async def update_balance():
    INTERVAL_EACH = 30
    while True:
        for coinItem in ["XMS"]:
            await asyncio.sleep(INTERVAL_EACH)
            print('Update balance: '+ coinItem)
            start = time.time()
            try:
                await store.sql_update_balances(coinItem)
            except Exception as e:
                print(e)
            end = time.time()


# Notify user
async def notify_new_tx_user():
    INTERVAL_EACH = 10
    while True:
        pending_tx = await store.sql_get_new_tx_table('NO', 'NO')
        if pending_tx and len(pending_tx) > 0:
            # let's notify_new_tx_user
            for eachTx in pending_tx:
                user_tx = None
                if eachTx['coin_name'] not in ["DOGE"]:
                    user_tx = await store.sql_get_userwallet_by_paymentid(eachTx['payment_id'], eachTx['coin_name'])
                else:
                    user_tx = await store.sql_get_userwallet_by_paymentid(eachTx['payment_id'], eachTx['coin_name'])
                if user_tx:
                    user_found = bot.get_user(id=int(user_tx['user_id']))
                    if user_found:
                        is_notify_failed = False
                        try:
                            msg = None
                            msg = "You got a new deposit: ```" + "Coin: {}\nTx: {}\nAmount: {}\nHeight: {:,.0f}".format(eachTx['coin_name'], eachTx['txid'], num_format_coin(eachTx['amount'], eachTx['coin_name']), eachTx['height']) + "```"
                            await user_found.send(msg)
                        except (discord.Forbidden, discord.errors.Forbidden) as e:
                            is_notify_failed = True
                            pass
                        update_notify_tx = await store.sql_update_notify_tx_table(eachTx['payment_id'], user_tx['user_id'], user_found.name, 'YES', 'NO' if is_notify_failed == False else 'YES')
                    else:
                        print('Can not find user id {} to notification tx: {}'.format(user_tx['user_id'], eachTx['txid']))
        else:
            print('No tx for notification')
        # print('Sleep {}s'.format(INTERVAL_EACH))
        await asyncio.sleep(INTERVAL_EACH)



# notify_new_tx_user_noconfirmation
async def notify_new_tx_user_noconfirmation():
    global redis_conn
    INTERVAL_EACH = config.interval.notify_tx
    await bot.wait_until_ready()
    while True:
        if config.notify_new_tx.enable_new_no_confirm == 1:
            key_tx_new = f'MoneroTipBot{bot.user.id}:NEWTX:NOCONFIRM'
            key_tx_no_confirmed_sent = f'MoneroTipBot{bot.user.id}:NEWTX:NOCONFIRM:SENT'
            try:
                openRedis()
                if redis_conn and redis_conn.llen(key_tx_new) > 0:
                    list_new_tx = redis_conn.lrange(key_tx_new, 0, -1)
                    list_new_tx_sent = redis_conn.lrange(key_tx_no_confirmed_sent, 0, -1) # byte list with b'xxx'
                    for tx in list_new_tx:
                        if tx not in list_new_tx_sent:
                            tx = tx.decode() # decode byte from b'xxx to xxx
                            key_tx_json = f'MoneroTipBot{bot.user.id}:NEWTX:' + tx
                            eachTx = None
                            try:
                                if redis_conn.exists(key_tx_json): eachTx = json.loads(redis_conn.get(key_tx_json).decode())
                            except Exception as e:
                                traceback.print_exc(file=sys.stdout)
                            if eachTx and eachTx['coin_name']:
                                user_tx = await store.sql_get_userwallet_by_paymentid(eachTx['payment_id'], eachTx['coin_name'], 'DISCORD')
                                if user_tx and eachTx['coin_name']: # in ["Coin1", "cOin2"]
                                    user_found = bot.get_user(id=int(user_tx['user_id']))
                                    if user_found:
                                        try:
                                            msg = None
                                            confirmation_number_txt = "{} needs {} confirmations.".format(eachTx['coin_name'], get_confirm_depth(eachTx['coin_name']))
                                            msg = "You got a new **pending** deposit: ```" + "Coin: {}\nTx: {}\nAmount: {}\nHeight: {:,.0f}\n{}".format(eachTx['coin_name'], eachTx['txid'], num_format_coin(eachTx['amount'], eachTx['coin_name']), eachTx['height'], confirmation_number_txt) + "```"
                                            await user_found.send(msg)
                                        except (discord.Forbidden, discord.errors.Forbidden) as e:
                                            pass
                                        redis_conn.lpush(key_tx_no_confirmed_sent, tx)
                                    else:
                                        print('Can not find user id {} to notification **pending** tx: {}'.format(user_tx['user_id'], eachTx['txid']))
                                # TODO: if no user
                                # elif eachTx['coin_name'] in ENABLE_COIN+ENABLE_COIN_DOGE+ENABLE_XMR:
                                #    redis_conn.lpush(key_tx_no_confirmed_sent, tx)
                            # if disable coin
                            else:
                                redis_conn.lpush(key_tx_no_confirmed_sent, tx)
            except Exception as e:
                traceback.print_exc(file=sys.stdout)
        await asyncio.sleep(INTERVAL_EACH)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send('This command cannot be used in private messages.')
    elif isinstance(error, commands.DisabledCommand):
        await ctx.send('Sorry. This command is disabled and cannot be used.')
    elif isinstance(error, commands.MissingRequiredArgument):
        #command = ctx.message.content.split()[0].strip('.')
        #await ctx.send('Missing an argument: try `.help` or `.help ' + command + '`')
        pass
    elif isinstance(error, commands.CommandNotFound):
        pass


async def is_owner(ctx):
    return ctx.author.id == config.discord.ownerID


# function to return if input string is ascii
def is_ascii(s):
    return all(ord(c) < 128 for c in s)


def hhashes(num) -> str:
    for x in ['H/s', 'KH/s', 'MH/s', 'GH/s', 'TH/s', 'PH/s', 'EH/s']:
        if num < 1000.0:
            return "%3.1f%s" % (num, x)
        num /= 1000.0
    return "%3.1f%s" % (num, 'TH/s')

def num_format_coin(amount, coin: str):
    return '{:,}'.format(float('%.12g' % (amount / get_decimal(coin.upper()))))


def get_cn_coin_from_address(CoinAddress: str):
    COIN_NAME = None
    if ((CoinAddress.startswith("5") or CoinAddress.startswith("7")) \
    and (len(CoinAddress) == 95 or len(CoinAddress) == 106)):
        addr = None
        # Try XMR
        try:
            addr = address_xmr(CoinAddress)
            COIN_NAME = "XMS"
            return COIN_NAME
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            pass
    return COIN_NAME


@register.error
async def register_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Missing your wallet address. '
                       f'You need to have a supported coin **address** after `register` command. Example: {config.discord.prefixCmd}register coin_address')
    return


@withdraw.error
async def withdraw_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Missing amount. '
                       f'You need to tell me **AMOUNT**.\nExample: {config.discord.prefixCmd}withdraw **1,000**')
    return


@tip.error
async def tip_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.message.add_reaction(EMOJI_ERROR)
        await ctx.send(f'{EMOJI_RED_NO} {ctx.author.mention} Missing arguments. '
                       f'You need to tell me **amount** and who you want to tip to.\nExample: {config.discord.prefixCmd}tip **1,000** <@{bot.user.id}>')
    return
    

def randomString(stringLength=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(stringLength))


def truncate(number, digits) -> float:
    stepper = pow(10.0, digits)
    return math.trunc(stepper * number) / stepper


def seconds_str(time: float):
    # day = time // (24 * 3600)
    # time = time % (24 * 3600)
    hour = time // 3600
    time %= 3600
    minutes = time // 60
    time %= 60
    seconds = time
    return "{:02d}:{:02d}:{:02d}".format(hour, minutes, seconds)


@click.command()
def main():
    bot.loop.create_task(update_balance())
    bot.loop.create_task(notify_new_tx_user())
    bot.loop.create_task(notify_new_tx_user_noconfirmation())
    bot.run(config.discord.token, reconnect=True)


if __name__ == '__main__':
    main()