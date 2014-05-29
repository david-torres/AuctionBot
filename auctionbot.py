from ScrollsSocketClient import ScrollsSocketClient
from fuzzywuzzy import process
from collections import OrderedDict
import threading
import random
import requests
import yaml
import logging
import time
import json
import re


class AuctionThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        global catalog
        global current_auction
        global starting_bid
        global current_bid
        global live
        global auction_start
        global auction_end
        global last_bid
        global completed_auction
        global restocking

        while True:
            if current_auction:
                continue

            # new auction
            unban_all()
            time.sleep(5)

            # wait for profile update
            time.sleep(10)

            restocking = True
            did_restock = False
            did_restock_once = False
            logging.info('Begin auto-restocking')
            while restocking:
                did_restock = restock()
                if did_restock:
                    if not did_restock_once:
                        did_restock_once = True
                    time.sleep(5)

            # notify room we're done restocking
            if did_restock_once:
                scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': 'Finished restocking. Pausing for requests.'})

            # wait for requests and library update
            time.sleep(30)

            # out of stock
            if len(catalog) <= 0:
                out_of_stock()
                break

            current_auction = select_from_catalog()
            logging.info('Starting auction for ' + current_auction['name'] + ', card id: ' + str(current_auction['id']))
            starting_bid = current_auction['starting_bid']
            current_bid = 0
            last_bid = None
            live = False
            completed_auction = None

            auction_start = time.time()
            auction_start_timer = 20
            auction_start_sleep = 20
            # auction_start_timer = 10
            # auction_start_sleep = 5

            # test values
            # auction_end_threshold_1 = 30  # 2m
            # auction_bid_threshold_1 = 10  # 1m
            # auction_end_threshold_2 = 60  # 4m
            # auction_bid_threshold_2 = 8  # 30s
            # auction_end_threshold_3 = 120  # 6m
            # auction_bid_threshold_3 = 5  # 15s

            # real values
            auction_end_threshold_1 = 120  # 2m
            auction_bid_threshold_1 = 60  # 30s
            auction_end_threshold_2 = 240  # 4m
            auction_bid_threshold_2 = 30  # 20s
            auction_end_threshold_3 = 360  # 6m
            auction_bid_threshold_3 = 15  # 10s
            auction_end_warn = False
            auction_end_warn_time = 0

            # auction_cancel_threshold = 60  # 3m
            # auction_cancel_warn_threshold = 20  # 2m30s
            auction_cancel_threshold = 180  # 1m20s
            auction_cancel_warn_threshold = 150  # 30s
            auction_cancel_warn = False

            # start the countdown timer
            while live is False:
                auction_start_countdown(auction_start_timer)
                time.sleep(auction_start_sleep)
                auction_start_timer -= auction_start_sleep
                if auction_start_timer <= 0:
                    live = True

            # announce live auction
            announce()
            while True:
                has_lock = lock.acquire(0)
                if not has_lock:
                    continue
                now = time.time()

                # we have a fresh bid, reset auction ending soon warning
                if last_bid > auction_end_warn_time:
                    auction_end_warn = False
                    auction_end_warn_time = last_bid

                # if we have at least one bid
                if last_bid:
                    # threshold 3 (6m)
                    if (now - auction_start) >= auction_end_threshold_3:
                        # auction has ended
                        if auction_end_warn and (now - auction_end_warn_time) > auction_bid_threshold_3:
                            lock.release()
                            won_auction()
                            if completed_auction_status():
                                break
                            else:
                                continue
                        # warn the auction will end soon
                        if (now - last_bid) >= auction_bid_threshold_3 and auction_end_warn is False:
                            auction_end_warn = True
                            auction_end_warn_time = time.time()
                            auction_end_countdown(auction_bid_threshold_3)
                    # threshold 2 (4m)
                    elif (now - auction_start) >= auction_end_threshold_2:
                        # auction has ended
                        if auction_end_warn and (now - auction_end_warn_time) > auction_bid_threshold_2:
                            lock.release()
                            won_auction()
                            if completed_auction_status():
                                break
                            else:
                                continue
                        # warn the auction will end soon
                        if (now - last_bid) >= auction_bid_threshold_2 and auction_end_warn is False:
                            auction_end_warn = True
                            auction_end_warn_time = time.time()
                            auction_end_countdown(auction_bid_threshold_2)
                    # threshold 1 (2m)
                    elif (now - auction_start) >= auction_end_threshold_1:
                        # auction has ended
                        if auction_end_warn and (now - auction_end_warn_time) > auction_bid_threshold_1:
                            lock.release()
                            won_auction()
                            if completed_auction_status():
                                break
                            else:
                                continue
                        # warn the auction will end soon
                        if (now - last_bid) >= auction_bid_threshold_1 and auction_end_warn is False:
                            auction_end_warn = True
                            auction_end_warn_time = time.time()
                            auction_end_countdown(auction_bid_threshold_1)

                else:
                    # no bids, cancel
                    if (now - auction_start) >= auction_cancel_threshold:
                        lock.release()
                        cancel_auction()
                        break
                    # warn the auction will be cancelled
                    if (now - auction_start) >= auction_cancel_warn_threshold and auction_cancel_warn is False:
                        auction_cancel_warn = True
                        auction_cancel_countdown(auction_cancel_threshold - auction_cancel_warn_threshold)
                lock.release()

global catalog
global starting_bid
global current_bid
global current_auction
global highest_bidder
global auction_start
global auction_end
global last_bid
global live
global card_list
global library
global banned
global profiles
global profiles_last_seen
global previous_bid
global previous_bidder
global completed_auction
global bot_profile
global restocking
global requested
global requesters
global lock
global prices
global gimmie_item

config_file = open('config.yaml', 'r')
config = yaml.load(config_file)

username = config['username']
password = config['password']
room = config['room']
admin_room = config['admin_room']
bot_name = config['bot_name']
bot_user = config['bot_user']
bot_profile = {}

admins = ['detour_', 'aTidwell', 'Tidwell2', 'Tidwell3', 'ScrollsToolbox']

bid_cmd = '!bid'
help_cmd = '!help'
announce_cmd = '!announce'
request_cmd = '!request'
ban_cmd = '!ban'
unban_cmd = '!unban'
hotstock_cmd = '!hotstock'
queue_cmd = '!queue'
gimmie_cmd = '!gimmie'

profiles = {}
to_be_removed = {}
catalog = {}
card_list = {}
library = {}
banned = {}
current_auction = None
starting_bid = None
current_bid = None
highest_bidder = None
previous_bid = None
previous_bidder = None
live = False
max_bid = 10000
min_bid = 10
last_bid = None
complete_auction_threshold = 60
ban_threshold = 3600
auction_end = None
completed_auction = None
restocking = False
requested = OrderedDict()
requesters = {}
prices = None
experimental_prices = None
clockwork_prices = None
hotstock = []
gimmie_item = None

auction_thread = AuctionThread()
lock = threading.Lock()


###
### MESSAGE RESPONSES
###

def run(message):
    """ This function is executed upon receiving the 'SignIn' event """
    global current_auction
    scrolls.send({'msg': 'JoinLobby'})

    # get the bot's profile data
    scrolls.subscribe('ProfileDataInfo', bot_profile_data)
    scrolls.send({'msg': 'ProfileDataInfo'})

    # populate the current list of scrolls
    scrolls.subscribe('CardTypes', card_types)
    scrolls.send({'msg': 'CardTypes'})

    # populate the library
    scrolls.subscribe('LibraryView', library_view)
    scrolls.send({'msg': 'LibraryView'})

    # subscribe to the RoomEnter event with function room_enter()
    scrolls.subscribe('RoomEnter', room_enter)

    # subscribe to the RoomInfo event with function room_info()
    scrolls.subscribe('RoomInfo', room_info)

    # subscribe to the RoomChatMessage event with function room_chat()
    scrolls.subscribe('RoomChatMessage', room_chat)

    # enter the room
    scrolls.send({'msg': 'RoomEnter', 'roomName': room})

    # enter the admin room
    scrolls.send({'msg': 'RoomEnter', 'roomName': admin_room})

    # start the main auction loop
    auction_thread.start()


def room_info(message):
    """ This function is executed upon receiving the 'RoomInfo' event """
    global current_auction
    global current_bid
    global live
    global profiles

    if 'roomName' in message and not message['roomName'] == room:
        return

    process_profiles(message)


def room_chat(message):
    """
    This function is executed upon receiving the 'RoomChatMessage' event
    Handles responding to chat commands
    """
    global restocking
    global live
    global banned

    if 'roomName' in message:
        if message['roomName'] not in [room, admin_room]:
            return

    # bot ignores messages from itself
    if 'text' in message and message['from'] == bot_user:
        return

    # bot ignores messages from banned users but not admins
    if 'from' in message and message['from'] in banned:
        if not message['from'] in admins:
            return

    # handle admin commands
    if 'from' in message and message['from'] in admins:
        if 'text' in message and ban_cmd in message['text']:
            ban_bidder(message)
        if 'text' in message and unban_cmd in message['text']:
            unban_bidder(message)
        if 'text' in message and gimmie_cmd in message['text']:
            gimmie(message)

    # handle !bid
    if 'text' in message and bid_cmd in message['text']:
        process_bid(message)

    # handle !request
    if 'text' in message and request_cmd in message['text']:
        process_request(message)

    # handle !announce
    if 'text' in message and announce_cmd == message['text']:
        if live:
            announce()

    # handle !help
    if 'text' in message and help_cmd == message['text']:
        help()

    # handle !hotstock
    if 'text' in message and hotstock_cmd == message['text']:
        announce_hotstock()

    # handle !queue
    if 'text' in message and queue_cmd == message['text']:
        announce_queue()

    time.sleep(1)


def room_enter(message):
    """
    This function is executed upon receiving the 'RoomEnter' event
    Announces the bot's presence in the room.
    """

    if message['roomName'] == room or message['roomName'] == admin_room:
        text = bot_name + ' is activated.'
        logging.info(text)
        if message['roomName'] == room:
            scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})
        else:
            scrolls.send({'msg': 'RoomChatMessage', 'roomName': admin_room, 'text': text})
    else:
        bid_reminder(message['roomName'])


def process_profiles(message):
    lock.acquire()
    global profiles
    global to_be_removed
    global highest_bidder
    global previous_bidder

    if 'updated' in message:
        new_profiles = message['updated']
        for new_profile in new_profiles:
            profiles[new_profile['name']] = new_profile
            if new_profile['name'] in to_be_removed.keys():
                del to_be_removed[new_profile['name']]
    elif 'removed' in message:
        rm_profiles = message['removed']
        for rm_profile in rm_profiles:
            if rm_profile['name'] == highest_bidder or rm_profile['name'] == previous_bidder:
                to_be_removed[rm_profile['name']] = time.time()
                continue
            else:
                if rm_profile['name'] in profiles.keys():
                    del profiles[rm_profile['name']]

    now = time.time()
    timeout = 60 * 10  # timeout 10m

    if len(to_be_removed) > 0:
        for name in list(to_be_removed):
            if to_be_removed[name] + timeout < now:
                del to_be_removed[name]

    logging.info('Updated user list. ' + ', '.join([name for name in profiles.keys()]))
    lock.release()


def restock():
    lock.acquire()
    global bot_profile
    global restocking

    pack_price = 1000
    pack_item_id = 180
    single_price = 100
    single_item_id = 137

    did_stock = False

    scrolls.subscribe('BuyStoreItemResponse', restock_items)

    if bot_profile['gold'] >= pack_price:
        scrolls.send({'itemId': pack_item_id, 'payWithShards': False, 'msg': 'BuyStoreItem'})
        logging.info('Stocked a pack: waiting to restock')
        did_stock = True
    elif bot_profile['gold'] >= single_price:
        scrolls.send({'itemId': single_item_id, 'payWithShards': False, 'msg': 'BuyStoreItem'})
        logging.info('Stocked a single: waiting to restock')
        did_stock = True
    else:
        scrolls.unsubscribe('BuyStoreItemResponse')
        scrolls.send({'msg': 'LibraryView'})
        restocking = False

    lock.release()
    return did_stock


def process_bid(message):
    """
    Validate and register bids
    """
    lock.acquire()
    global current_auction
    global starting_bid
    global current_bid
    global highest_bidder
    global last_bid
    global live
    global banned
    global previous_bidder
    global previous_bid
    global profiles

    bidder = message['from']

    if not bidder in profiles:
        logging.error('User has submitted a bid but is not in known profiles')
        logging.error(str(message))
        logging.error(str(profiles))
        text = 'ERROR! Failed to register bid from ' + bidder + '. This is a known bug, please re-enter the room'
        scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})
        lock.release()
        return

    user = profiles[bidder]

    bid = message['text'].split(bid_cmd)[1].strip()
    bid_re = re.match('^((\d+)\s?g?){1}', bid)

    if not live or not current_auction:
        text = bidder + ', No auctions are currently active.'
    elif bidder in banned:
        text = 'Invalid bid from: ' + bidder + ', you are banned.'
    elif not user['acceptTrades']:
        text = 'Invalid bid from: ' + bidder + ', you must accept trades.'
    elif not bid_re:
        text = 'Invalid bid from: ' + bidder + ''
    elif not bid_re.group(2).isdigit():
        text = 'Invalid bid from: ' + bidder + ''
    else:
        bid_amount = int(bid_re.group(2))
        if bidder == highest_bidder:
            text = 'Invalid bid from: ' + bidder + ', you are already the highest bidder. Current bid: ' + str(current_bid)
        elif current_bid > 0 and bid_amount <= current_bid:
            text = 'Invalid bid from: ' + bidder + ', bid too low. Current bid: ' + str(current_bid)
        elif current_bid == 0 and bid_amount < starting_bid:
            text = 'Invalid bid from: ' + bidder + ', bidding starts at: ' + str(starting_bid)
        elif current_bid > 0 and bid_amount < (current_bid + min_bid):
            text = 'Invalid bid from: ' + bidder + ', minimum bid is: ' + str(current_bid + min_bid)
        elif bid_amount > max_bid:
            text = 'Invalid bid from: ' + bidder + ', bid is greater than max bid.'
        else:
            if highest_bidder:
                previous_bidder = highest_bidder
                previous_bid = current_bid

            current_bid = bid_amount
            highest_bidder = bidder
            last_bid = time.time()

            text = 'Registered bid for ' + current_auction['name'] + ' from: ' + bidder + ', Bid: ' + str(bid_amount) + 'g'
            if previous_bidder:
                text += '\n' + previous_bidder + ' has been outbid!'
            announce()
    if current_auction and 'id' in current_auction:
        logging.info(text + ', card id: ' + str(current_auction['id']))
    else:
        logging.info(text)
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})
    lock.release()


def won_auction():
    lock.acquire()
    global current_auction
    global current_bid
    global highest_bidder
    global auction_end
    global last_bid
    global live

    live = False
    user = profiles[highest_bidder]
    auction_end = time.time()

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'SOLD! Auction: ' + current_auction['name'] + '\n'
    text += 'High bidder: ' + highest_bidder + '\n'
    text += 'Closing bid: ' + str(current_bid) + 'g'

    logging.info(text + ', card id: ' + str(current_auction['id']))
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})

    send_trade_invite(user)
    lock.release()


def resume_auction():
    lock.acquire()
    global current_auction
    global current_bid
    global highest_bidder
    global last_bid
    global auction_end
    global previous_bid
    global previous_bidder
    global live
    global completed_auction

    highest_bidder = previous_bidder
    current_bid = previous_bid

    if previous_bidder:
        text = '[[ ' + bot_name + ' ]]\n'
        text += 'Resuming! Auction: ' + current_auction['name'] + '\n'
        text += 'High bidder: ' + highest_bidder + '\n'
        text += 'Current bid: ' + str(current_bid) + 'g'

        logging.info(text + ', card id: ' + str(current_auction['id']))
        scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})

        auction_end = None
        previous_bid = None
        previous_bidder = None
        last_bid = time.time()
        live = True

        # signal auction thread that we need to continue
        completed_auction = False
        lock.release()
    else:
        lock.release()
        cancel_auction()


def complete_auction():
    lock.acquire()
    global current_auction
    global current_bid
    global highest_bidder
    global last_bid
    global auction_end
    global previous_bid
    global previous_bidder
    global completed_auction

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'COMPLETED TRADE! Auction: ' + current_auction['name'] + '\n'
    text += 'High bidder: ' + highest_bidder + '\n'
    text += 'Closing bid: ' + str(current_bid) + 'g'

    logging.info(text + ', card id: ' + str(current_auction['id']))
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})
    scrolls.send({'msg': 'LibraryView'})
    scrolls.send({'msg': 'ProfileDataInfo'})

    current_auction = None
    current_bid = None
    highest_bidder = None
    last_bid = None
    auction_end = None
    previous_bid = None
    previous_bidder = None

    # signal auction thread that we finished
    completed_auction = True
    lock.release()


def cancel_auction():
    lock.acquire()
    global current_auction
    global highest_bidder
    global auction_end
    global current_bid
    global last_bid
    global previous_bid
    global previous_bidder
    global live
    global completed_auction
    global catalog

    live = False
    catalog.append(current_auction)

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Cancelled auction: ' + current_auction['name']

    logging.info(text)
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})

    current_auction = None
    current_bid = None
    highest_bidder = None
    last_bid = None
    auction_end = None
    previous_bidder = None
    previous_bid = None

    # signal auction thread that we finished
    completed_auction = True
    lock.release()


def gimmie(message):
    lock.acquire()
    """
    Respond to the !request command
    """
    global card_list
    global catalog
    global profiles
    global gimmie_item

    requester = message['from']
    requested_scroll = message['text'].split(gimmie_cmd)[1].strip()

    scroll_exists = False
    scroll_name = None
    for card_id, card_type in card_list.iteritems():
        if card_type['name'].lower() == requested_scroll.lower():
            scroll_name = card_type['name']
            scroll_exists = True
            break

    # fuzzy match
    if not scroll_exists:
        card_names = [card_type['name'] for card_id, card_type in card_list.iteritems()]
        fuzzy_match = process.extractOne(requested_scroll, card_names)
        if fuzzy_match and fuzzy_match[1] > 70:
            scroll_name = fuzzy_match[0]
            scroll_exists = True

    if not scroll_exists:
        text = 'Cannot give to ' + requester + '. No scroll named ' + requested_scroll
    else:
        scroll_found_in_catalog = False
        for item in catalog:
            if item['name'] == scroll_name:
                scroll_found_in_catalog = True
                gimmie_item = item
                break

        if not scroll_found_in_catalog:
            text = 'Sorry ' + requester + '. ' + scroll_name + ' is out of stock.'
            scrolls.send({'msg': 'RoomChatMessage', 'roomName': admin_room, 'text': text})
        else:
            user = profiles[requester]
            scrolls.subscribe('TradeResponse', gimmie_invite_response)
            logging.info('Sent gimmie invite to: ' + user['name'] + ', card id: ' + str(gimmie_item['id']))
            scrolls.send({'msg': 'TradeInvite', 'profileId': user['profileId']})
    lock.release()


def send_trade_invite(user):
    scrolls.subscribe('TradeResponse', trade_invite_response)
    logging.info('Sent trade invite to: ' + user['name'] + ', card id: ' + str(current_auction['id']))
    scrolls.send({'msg': 'TradeInvite', 'profileId': user['profileId']})


def trade_invite_response(message):
    global bot_name
    global bot_profile
    global highest_bidder
    global current_auction
    global current_bid
    global auction_end

    if not auction_end:
        return

    if not current_auction:
        logging.error('Trade invite response but no current auction')
        return

    if not highest_bidder:
        logging.error('Trade invite response but no high bidder')
        return

    if not message['to']['name'] == highest_bidder:
        logging.error('Trade invite response but not to highest_bidder')
        return

    # bidder has accepted the trade invite
    if message['status'] == 'ACCEPT':
        # add the card to the trade
        scrolls.subscribe('TradeView', trade_view_response)

        logging.info('Adding card to trade: ' + current_auction['name'] + ', card id: ' + str(current_auction['id']))
        scrolls.send({'msg': 'TradeAddCards', 'cardIds': [current_auction['id']]})
    else:
        # bidder declinded the trade invite, BAN!
        ban(highest_bidder)
        text = '[[ ' + bot_name + ' ]]\n'
        text += 'DECLINED TRADE! Auction: ' + current_auction['name'] + '\n'
        text += 'Banned: ' + highest_bidder

        logging.info('Trade was declined by ' + highest_bidder + ', card id: ' + str(current_auction['id']))
        scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})
        resume_auction()


def gimmie_invite_response(message):
    global gimmie_item
    if message['status'] == 'ACCEPT':
        scrolls.subscribe('TradeView', gimmie_view_response)
        logging.info('Adding card to trade: ' + gimmie_item['name'] + ', card id: ' + str(gimmie_item['id']))
        scrolls.send({'msg': 'TradeAddCards', 'cardIds': [gimmie_item['id']]})


def trade_view_response(message):
    global current_auction
    global current_bid
    global auction_end
    global highest_bidder

    if not auction_end:
        return

    if not current_auction:
        logging.error('Trade view response but no current auction')
        return

    if not highest_bidder:
        logging.error('Trade view response but no high bidder')
        return

    if not message['to']['profile']['name'] == highest_bidder:
        logging.error('Trade view response but not to highest_bidder')
        return

    if 'cardIds' in message['from'] and len(message['from']['cardIds']) == 0:
        logging.info('Card not added to trade' + ', card id: ' + current_auction['id'])
        scrolls.send({'msg': 'TradeAddCards', 'cardIds': [current_auction['id']]})
        return

    # bidder has accepted and traded the correct amount of gold
    if message['to']['accepted'] and message['to']['gold'] == current_bid:
        logging.info('Accepted trade with ' + message['to']['profile']['name'] + ', card id: ' + str(current_auction['id']))
        logging.info('Gold: ' + str(message['to']['gold']))
        scrolls.send({'msg': 'TradeAcceptBargain'})
        scrolls.unsubscribe('TradeView')
        complete_auction()
    else:
        # bidder takes too long to finish the trade, cancel
        if time.time() - auction_end > complete_auction_threshold:
            logging.info('Cancelled trade with ' + message['to']['profile']['name'] + ', card id: ' + str(current_auction['id']))
            scrolls.unsubscribe('TradeResponse')
            scrolls.send({'msg': 'TradeCancel'})
            ban(highest_bidder)
            text = '[[ ' + bot_name + ' ]]\n'
            text += 'FAILED TRADE! Auction: ' + current_auction['name'] + '\n'
            text += 'Banned: ' + highest_bidder
            scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})
            resume_auction()


def gimmie_view_response(message):
    global gimmie_item
    if message['to']['accepted']:
        scrolls.send({'msg': 'TradeAcceptBargain'})
        scrolls.unsubscribe('TradeView')
        gimmie_item = None


def auction_start_countdown(countdown_time):
    """
    Countdown to next auction message
    """
    global current_auction

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Next auction: ' + current_auction['name'] + '\n'
    text += 'Starting in ' + str(countdown_time) + ' seconds\n'
    text += '-----\n'
    text += 'Send !help for commands'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def auction_end_countdown(ending_in):
    global current_auction
    global current_bid
    global highest_bidder

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Ending soon! Auction: ' + current_auction['name'] + '\n'
    text += 'High bidder: ' + highest_bidder + '\n'
    text += 'Current bid: ' + str(current_bid) + 'g\n'
    text += 'Ending in ' + str(ending_in) + ' seconds'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def auction_cancel_countdown(ending_in):
    global current_auction
    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Warning! Auction: ' + current_auction['name'] + '\n'
    text += 'Ending in ' + str(ending_in) + ' seconds'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def out_of_stock():
    """
    Out of stock message sent when we run out of cards to sell
    """
    text = '[[ ' + bot_name + ' ]]\n'
    text += 'OUT OF STOCK'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def process_request(message):
    lock.acquire()
    """
    Respond to the !request command
    """
    global requested
    global requesters
    global card_list
    global catalog
    global current_auction

    requester = message['from']
    requested_scroll = message['text'].split(request_cmd)[1].strip()

    scroll_exists = False
    scroll_name = None
    for card_id, card_type in card_list.iteritems():
        if card_type['name'].lower() == requested_scroll.lower():
            scroll_name = card_type['name']
            scroll_exists = True
            break

    # fuzzy match
    if not scroll_exists:
        card_names = [card_type['name'] for card_id, card_type in card_list.iteritems()]
        fuzzy_match = process.extractOne(requested_scroll, card_names)
        if fuzzy_match and fuzzy_match[1] > 70:
            scroll_name = fuzzy_match[0]
            scroll_exists = True

    if not scroll_exists:
        text = 'Invalid request from ' + requester + '. No scroll named ' + requested_scroll
    else:
        scroll_found_in_catalog = False
        for item in catalog:
            if current_auction and item['id'] == current_auction['id']:
                continue
            if item['name'] == scroll_name:
                scroll_found_in_catalog = True
                break

        if not scroll_found_in_catalog:
            text = 'Sorry ' + requester + '. ' + scroll_name + ' is out of stock.'
        else:
            if requester in requesters.keys():
                previous_request = requesters[requester]
                requested[previous_request]['score'] -= 1

            requesters[requester] = scroll_name

            if scroll_name in requested.keys():
                requested[scroll_name]['score'] += 1
            else:
                requested[scroll_name] = {
                    'score': 1,
                    'timestamp': time.time()
                }

                requested = requested.items()
                requested.sort(key=lambda (k,d): (d['timestamp'],-d['score'],))
                requested = OrderedDict([(k, v) for k,v in requested if v['score'] > 0])

            text = 'Registered request from ' + requester + '. ' + scroll_name
            text += ' requested ' + str(requested[scroll_name]['score']) + ' times'
            logging.info(text)

    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})
    lock.release()



def announce():
    """
    Respond to the !announce command
    """
    global current_auction
    global current_bid
    global starting_bid
    global highest_bidder

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Current auction: ' + current_auction['name'] + '.\n'
    if highest_bidder:
        text += 'High bidder: ' + highest_bidder + '\n'
    else:
        text += 'No bids yet\n'

    if current_bid > 0:
        text += 'Current bid: ' + str(current_bid) + 'g\n'
    else:
        text += 'Starting bid: ' + str(starting_bid) + 'g\n'
    text += '-----\n'
    text += 'Send !help for commands'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def help():
    """
    Respond to the !help command
    """
    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Send " !bid GOLD " to bid on the current auction\n'
    text += 'Send " !request SCROLL " to request a specific scroll\n'
    text += 'Send " !announce " to see the current auction\n'
    text += 'Send " !hotstock " to see popular scrolls in stock\n'
    text += 'Send " !queue " to see the auction queue'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


###
### ONE-OFF RESPONSES
###

def announce_hotstock():
    global hotstock
    text = ', '.join(hotstock)
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def announce_queue():
    global requested

    if len(requested) > 0:
        text = 'Auction queue is: ' + ', '.join(requested)
    else:
        text = 'Queue is empty'

    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def ban_bidder(message):
    bidder = message['text'].split(ban_cmd)[1].strip()
    ban(bidder)
    text = 'Banned: ' + bidder
    logging.info(text)
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def unban_bidder(message):
    bidder = message['text'].split(unban_cmd)[1].strip()
    unban(bidder)
    text = 'Unbanned: ' + bidder
    logging.info(text)
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def restock_items(message):
    global card_list
    stocked = []
    for card in message['cards']:
        card_type = card_list[card['typeId']]
        stocked.append(card_type['name'])

    text = 'Stocked: ' + ', '.join(stocked)
    logging.info(text)
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})
    time.sleep(5)
    scrolls.send({'msg': 'ProfileDataInfo'})


def bid_reminder(trade_room):
    global current_bid
    global current_auction
    global gimmie_item

    if gimmie_item:
        return
    text = 'You bid ' + str(current_bid) + 'g for ' + current_auction['name'] + '\n'
    text += 'Please enter the correct amount and press Accept to complete the trade.'
    logging.info(text + ', card id: ' + str(current_auction['id']))
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': trade_room, 'text': text})


def card_types(message):
    """
    Save the current master list of cards
    """
    global card_list
    for card in message['cardTypes']:
        card_list[card['id']] = card


def library_view(message):
    """
    Save our current library
    """
    global library
    global bot_profile

    if message['profileId'] == bot_profile['id']:
        library = message['cards']
        sync_collection(library)
        populate_catalog()


def bot_profile_info(message):
    """
    Retrieve's the bot's own profile
    """
    global bot_profile
    if 'profile' in message and 'name' in message['profile'] and message['profile']['name'] == bot_user:
        bot_profile.update(message['profile'])


def bot_profile_data(message):
    """
    Retrieve's the bot's data
    """
    global bot_profile
    bot_profile.update(message['profileData'])
    logging.info('Purse: ' + str(bot_profile['gold']))


def notify_requesters(requested_scroll):
    global requesters
    requesters_str = ', '.join([requestee for requestee, scroll in requesters.iteritems() if scroll == requested_scroll])
    for requestee in dict(requesters).keys():
        if requesters[requestee] == requested_scroll:
            requesters.pop(requestee)

    logging.info('notifying ' + requesters_str + ' ' + requested_scroll + ' is up for auction')
    text = 'Notification: ' + requesters_str + '\n' + requested_scroll + ' is up for auction.'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def select_from_catalog():
    lock.acquire()
    global catalog
    global requested
    global card_list

    auction_item = None
    if len(requested) > 0:
        top_request = requested.keys()[0]
        for catalog_index, catalog_item in enumerate(catalog):
            if catalog_item['name'] == top_request:
                requested.popitem(0)
                notify_requesters(top_request)
                auction_item = catalog.pop(catalog_index)
                break

    else:
        auction_item = catalog.pop(0)

    lock.release()
    return auction_item


def populate_catalog():
    """
    Fetches the latest prices from scrollsguide and populates our catalog of rares and uncommons
    """
    lock.acquire()
    global library
    global catalog
    global card_list
    global prices
    global experimental_prices
    global clockwork_prices
    global current_auction

    jank_list = []
    seen_scrolls = {}

    if not prices:
        prices_r = requests.get('http://a.scrollsguide.com/prices')
        prices = prices_r.json()['data']

    if not experimental_prices:
        experimental_prices_r = requests.get('http://a.scrollsguide.com/experimentalprices')
        experimental_prices = experimental_prices_r.json()['data']

    if not clockwork_prices:
        clockwork_prices_r = requests.get('http://www.kimonolabs.com/api/4pxmtz8o?apikey=792af1db42af6a41419730274e89d4d2')
        clockwork_prices = clockwork_prices_r.json()['results']['prices']

    if prices:
        catalog = []
        for library_item in library:
            if library_item['tradable'] is True:
                check_experimental_prices = False
                check_clockwork_prices = False

                if current_auction and current_auction['id'] == library_item['id']:
                    continue

                # get the base card
                card_type = card_list[library_item['typeId']]

                if library_item['level'] == 0:
                    if card_type['id'] in seen_scrolls.keys():
                        seen_scrolls[card_type['id']] = seen_scrolls[card_type['id']] + 1
                    else:
                        seen_scrolls[card_type['id']] = 1

                    if seen_scrolls[card_type['id']] > 7:
                        jank_list.append(library_item['id'])

                # pricing
                for price in prices:
                    if price['id'] == library_item['typeId']:
                        buy = price['buy']
                        if buy > 0:
                            starting_bid = buy
                        else:
                            check_experimental_prices = True
                            continue

                        auction_item = {
                            'id': library_item['id'],
                            'type_id': card_type['id'],
                            'name': card_type['name'],
                            'starting_bid': starting_bid
                        }
                        catalog.append(auction_item)

                if check_experimental_prices:
                    for price in experimental_prices:
                        if price['id'] == library_item['typeId']:
                            buy = price['buy']['price']
                            if buy > 0:
                                starting_bid = buy
                            else:
                                check_clockwork_prices = True
                                continue

                            auction_item = {
                                'id': library_item['id'],
                                'type_id': card_type['id'],
                                'name': card_type['name'],
                                'starting_bid': starting_bid
                            }
                            catalog.append(auction_item)

                if check_clockwork_prices:
                    for price in clockwork_prices:
                        if price['name'] == card_type['name']:
                            buy = int(price['buy'])
                            if buy > 0:
                                starting_bid = buy
                            else:
                                continue

                            auction_item = {
                                'id': library_item['id'],
                                'type_id': card_type['id'],
                                'name': card_type['name'],
                                'starting_bid': starting_bid
                            }
                            catalog.append(auction_item)

        sell_jank(jank_list)
        logging.info('Populated catalog, ' + str(len(catalog)) + ' scrolls for sale')
        random.shuffle(catalog)
        process_hotstock()
    lock.release()


def sell_jank(jank_list):
    scrolls.send({'msg': 'SellCards', 'cardIds': jank_list})


def sync_collection(library):
    sync_r = requests.post('http://scrollstoolbox.com/collection/update?inGameName=' + bot_user, data=json.dumps(library))
    logging.info(sync_r.text)


def process_hotstock():
    global hotstock
    global catalog

    card_counts = {}
    for card in catalog:
        if card['name'] in card_counts:
            card_counts[card['name']] += 1
        else:
            card_counts[card['name']] = 1

    hotstock = [name for name, count in card_counts.iteritems() if count <= 3]


def ban(bidder):
    """
    add a user to the ban list
    """
    global banned
    if bidder:
        logging.info('Banned ' + bidder)
        banned.update({bidder: time.time()})


def unban(bidder):
    global banned
    if bidder in banned:
        logging.info('Unbanned: ' + bidder)
        banned.pop(bidder)


def unban_all():
    """
    unban users who have served their time
    """
    global banned
    banned_local = dict(banned)
    for bad_user, time_banned in banned_local.iteritems():
        if time.time() - time_banned > ban_threshold:
            logging.info('Unbanned ' + bad_user)
            banned.pop(bad_user)


def completed_auction_status():
    """
    The purpose of this function is to block the
    main auction loop until we are certain an auction
    has been completed or not (happens async)
    """
    global completed_auction
    while True:
        if completed_auction is True:
            completed_auction = None
            return True
        elif completed_auction is False:
            completed_auction = None
            return False
        else:
            time.sleep(1)

###
### APP INIT
###

# init logging
logging.basicConfig(filename="app.log", level=logging.INFO)

# init the scrolls client
scrolls = ScrollsSocketClient(username, password)

# subscribe to the FirstConnect event with function run()
scrolls.subscribe('FirstConnect', run)
scrolls.subscribe('ProfileInfo', bot_profile_info)

# login to the server
scrolls.login()
