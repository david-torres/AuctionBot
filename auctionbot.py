from ScrollsSocketClient import ScrollsSocketClient
import threading
import random
import requests
import time
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

        while (1):
            if current_auction:
                continue

            # new auction
            time.sleep(10)
            unban()

            # out of stock
            if len(catalog) <= 0:
                out_of_stock()
                break

            current_auction = catalog.pop(0)
            starting_bid = current_auction[1]
            current_bid = current_auction[1]
            last_bid = None
            live = False
            completed_auction = None

            auction_start = time.time()
            auction_start_timer = 60
            auction_start_sleep = 20
            # auction_start_timer = 10
            # auction_start_sleep = 5

            # auction_end_threshold_1 = 30  # 2m
            # auction_bid_threshold_1 = 10  # 1m
            auction_end_threshold_1 = 120  # 2m
            auction_bid_threshold_1 = 60  # 1m
            auction_end_threshold_2 = 240  # 4m
            auction_bid_threshold_2 = 30  # 30s
            auction_end_threshold_3 = 360  # 6m
            auction_bid_threshold_3 = 15  # 15s
            auction_end_warn = False
            auction_end_warn_time = 0

            # auction_cancel_threshold = 30  # 3m
            # auction_cancel_warn_threshold = 10  # 2m30s
            auction_cancel_threshold = 180  # 3m
            auction_cancel_warn_threshold = 150  # 2m30s
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
            while (1):
                now = time.time()

                # we have a fresh bid, reset auction ending soon warning
                if last_bid > auction_end_warn_time:
                    auction_end_warn = False
                    auction_end_warn_time = last_bid

                # if we have at least one bid
                if last_bid:
                    # threshold 3 (6m)
                    if now - auction_start > auction_end_threshold_3:
                        # auction has ended
                        if now - last_bid > auction_end_threshold_3:
                            won_auction()
                            if completed_auction_status():
                                break
                            else:
                                continue
                        # warn the auction will end soon
                        if now - last_bid >= auction_bid_threshold_3 and auction_end_warn is False:
                            auction_end_warn = True
                            auction_end_warn_time = last_bid
                            auction_end_countdown(auction_bid_threshold_3)
                    # threshold 2 (4m)
                    elif now - auction_start > auction_end_threshold_2:
                        # auction has ended
                        if now - last_bid > auction_end_threshold_2:
                            won_auction()
                            if completed_auction_status():
                                break
                            else:
                                continue
                        # warn the auction will end soon
                        if now - last_bid >= auction_bid_threshold_2 and auction_end_warn is False:
                            auction_end_warn = True
                            auction_end_warn_time = last_bid
                            auction_end_countdown(auction_bid_threshold_2)
                    # threshold 1 (2m)
                    elif now - auction_start > auction_end_threshold_1:
                        # auction has ended
                        if now - last_bid > auction_end_threshold_1:
                            won_auction()
                            if completed_auction_status():
                                break
                            else:
                                continue
                        # warn the auction will end soon
                        if now - last_bid >= auction_bid_threshold_1 and auction_end_warn is False:
                            auction_end_warn = True
                            auction_end_warn_time = last_bid
                            auction_end_countdown(auction_bid_threshold_1)

                else:
                    # no bids, cancel
                    if now - auction_start >= auction_cancel_threshold:
                        cancel_auction()
                        break
                    # warn the auction will be cancelled
                    if now - auction_start >= auction_cancel_warn_threshold and auction_cancel_warn is False:
                        auction_cancel_warn = True
                        auction_cancel_countdown(auction_cancel_threshold - auction_cancel_warn_threshold)

global catalog
global starting_bid
global current_bid
global current_auction
global highest_bidder
global auction_start
global auction_end
global last_bid
global live
global all_scrolls
global library
global banned
global profiles
global previous_bid
global previous_bidder
global completed_auction

email = 'scrolls.auctionbot@gmail.com'
password = '98*psq2K&t7MPv72$@&FJe7z'

bot_name = 'AuctionBot v0.1a'
bot_user = 'AuctionBot'
bot_profile = None

announce_cmd = '!announce'
bid_cmd = '!bid'
help_cmd = '!help'

room = 'auction'
profiles = []
catalog = []
current_auction = None
starting_bid = None
current_bid = None
highest_bidder = None
previous_bid = None
previous_bidder = None
live = False
max_bid = 5000
last_bid = None
all_scrolls = None
library = None
complete_auction_threshold = 60
ban_threshold = 3600
auction_end = None
banned = {}
completed_auction = None

auction_thread = AuctionThread()


def run(message):
    global current_auction

    """ This function is executed upon receiving the 'SignIn' event """

    # populate the current list of scrolls
    scrolls.subscribe('CardTypes', card_types)
    scrolls.send({'msg': 'CardTypes'})

    # populate the library
    scrolls.subscribe('LibraryView', library)
    scrolls.send({'msg': 'LibraryView'})

    # subscribe to the RoomEnter event with function room_enter()
    scrolls.subscribe('RoomEnter', room_enter)

    # subscribe to the RoomInfo event with function room_info()
    scrolls.subscribe('RoomInfo', room_info)

    # subscribe to the RoomChatMessage event with function room_chat()
    scrolls.subscribe('RoomChatMessage', room_chat)

    # enter the room
    scrolls.send({'msg': 'RoomEnter', 'roomName': room})

    # start the main auction loop
    auction_thread.start()


def room_info(message):
    """ This function is executed upon receiving the 'RoomInfo' event """
    global current_auction
    global current_bid
    global live
    global profiles

    profiles = profiles + message['profiles']

    if live:
        announce()


def room_chat(message):
    """
    This function is executed upon receiving the 'RoomChatMessage' event
    Handles responding to chat commands
    """
    global current_auction
    global current_bid
    global max_bid
    global live

    # bot ignores messages from itself
    if 'text' in message and message['from'] == bot_user:
        return

    # handle !bid
    if 'text' in message and bid_cmd in message['text']:
        process_bid(message)

    # handle !announce
    if 'text' in message and announce_cmd == message['text']:
        if live:
            announce()

    # handle !help
    if 'text' in message and help_cmd == message['text']:
        help()


def room_enter(message):
    """
    This function is executed upon receiving the 'RoomEnter' event
    Announces the bot's presence in the room.
    """
    if message['roomName'] == room:
        text = bot_name + ' is activated.'
        scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def process_bid(message):
    """
    Validate and register bids
    """
    global current_auction
    global starting_bid
    global current_bid
    global highest_bidder
    global last_bid
    global live
    global banned
    global previous_bidder
    global previous_bid

    bidder = message['from']
    user = get_user(bidder)
    bid = message['text'].split(bid_cmd)[1].strip()
    bid_re = re.match('^((\d+)\s?g?){1}', bid)

    if not live:
        text = 'No auctions are currently active.'
    elif bidder in banned:
        text = 'Invalid bid from: "' + bidder + '", you are banned.'
    elif not user['acceptTrades']:
        text = 'Invalid bid from: "' + bidder + '", you must accept trades.'
    elif not bid_re:
        text = 'Invalid bid from: "' + bidder + '"'
    elif not bid_re.group(2).isdigit():
        text = 'Invalid bid from: "' + bidder + '"'
    else:
        bid_amount = int(bid_re.group(2))
        if bidder == highest_bidder:
            text = 'Invalid bid from: "' + bidder + '", you are already the highest bidder. Current bid: ' + str(current_bid)
        elif bid_amount <= current_bid:
            text = 'Invalid bid from: "' + bidder + '", bid too low. Current bid: ' + str(current_bid)
        elif bid_amount > max_bid:
            text = 'Invalid bid from: "' + bidder + '", bid is greater than max bid.'
        else:
            if highest_bidder:
                previous_bidder = highest_bidder
                previous_bid = current_bid

            current_bid = bid_amount
            highest_bidder = bidder
            last_bid = time.time()

            text = 'Registered bid from: "' + bidder + '", Bid: ' + str(bid_amount) + 'g'
            announce()

    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def won_auction():
    global current_auction
    global current_bid
    global highest_bidder
    global auction_end
    global last_bid
    global live

    live = False
    user = get_user(highest_bidder)
    auction_end = time.time()

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'SOLD! Auction: ' + current_auction[0] + '\n'
    text += 'High bidder: ' + highest_bidder + '\n'
    text += 'Closing bid: ' + str(current_bid) + 'g\n'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})

    send_trade_invite(user)


def resume_auction():
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
        text += 'Resuming! Auction: ' + current_auction[0] + '\n'
        text += 'High bidder: ' + highest_bidder + '\n'
        text += 'Current bid: ' + str(current_bid) + 'g\n'
        scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})

        auction_end = None
        previous_bid = None
        previous_bidder = None
        last_bid = time.time()
        live = True

        # signal auction thread that we need to continue
        completed_auction = False
    else:
        cancel_auction()


def complete_auction():
    global current_auction
    global current_bid
    global highest_bidder
    global last_bid
    global auction_end
    global previous_bid
    global previous_bidder
    global completed_auction

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'COMPLETED TRADE! Auction: ' + current_auction[0] + '\n'
    text += 'High bidder: ' + highest_bidder + '\n'
    text += 'Closing bid: ' + str(current_bid) + 'g\n'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})

    current_auction = None
    current_bid = None
    highest_bidder = None
    last_bid = None
    auction_end = None
    previous_bid = None
    previous_bidder = None

    # signal auction thread that we finished
    completed_auction = True


def cancel_auction():
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
    text += 'Cancelled auction: ' + current_auction[0]
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


def send_trade_invite(user):
    scrolls.subscribe('TradeResponse', trade_invite_response)
    scrolls.send({'msg': 'TradeInvite', 'profile': user['id']})


def trade_invite_response(message):
    global bot_name
    global bot_profile
    global highest_bidder
    global current_auction
    global current_bid

    # bidder has accepted the trade invite
    if message['status'] == 'ACCEPT':
        # add the card to the trade
        scrolls.subscribe('TradeView', trade_view_response)
        card = find_scroll_in_library(current_auction[0])
        card_id = int(card['id'])
        scrolls.send({'msg': 'TradeAddCards', 'cardIds': [card_id]})
    else:
        # bidder declinded the trade invite, BAN!
        ban(highest_bidder)
        text = '[[ ' + bot_name + ' ]]\n'
        text += 'DECLINED TRADE! Auction: ' + current_auction[0] + '\n'
        text += 'Banned: ' + highest_bidder + '\n'
        scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})
        resume_auction()


def trade_view_response(message):
    global complete_auction_threshold
    global current_bid
    global auction_end

    if not auction_end:
        return

    # bidder has accepted and traded the correct amount of gold
    if message['to']['accepted'] and message['to']['gold'] == current_bid:
        scrolls.send({'msg': 'TradeAcceptBargain'})
        scrolls.unsubscribe('TradeView')
        complete_auction()
    else:
        if time.time() - auction_end > complete_auction_threshold:
            scrolls.unsubscribe('TradeResponse')
            scrolls.send({'msg': 'TradeCancel'})
            ban(highest_bidder)
            text = '[[ ' + bot_name + ' ]]\n'
            text += 'FAILED TRADE! Auction: ' + current_auction[0] + '\n'
            text += 'Banned: ' + highest_bidder + '\n'
            scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})
            resume_auction()


def auction_start_countdown(countdown_time):
    """
    Countdown to next auction message
    """
    global current_auction

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Next auction: ' + current_auction[0] + '\n'
    text += 'Starting in ' + str(countdown_time) + ' seconds\n'
    text += '-----\n'
    text += 'Send !help for commands'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def auction_end_countdown(ending_in):
    global current_auction
    global current_bid
    global highest_bidder

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Ending soon! Auction: ' + current_auction[0] + '\n'
    text += 'High bidder: ' + highest_bidder + '\n'
    text += 'Current bid: ' + str(current_bid) + 'g\n'
    text += 'Ending in ' + str(ending_in) + ' seconds'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def auction_cancel_countdown(ending_in):
    global current_auction
    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Warning! Auction: ' + current_auction[0] + '\n'
    text += 'Ending in ' + str(ending_in) + ' seconds'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def out_of_stock():
    """
    Out of stock message sent when we run out of cards to sell
    """
    text = '[[ ' + bot_name + ' ]]\n'
    text += 'OUT OF STOCK'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def announce():
    """
    Respond to the !announce command
    """
    global current_auction
    global current_bid
    global highest_bidder

    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Current auction: ' + current_auction[0] + '.\n'
    if highest_bidder:
        text += 'High bidder: ' + highest_bidder + '\n'
    else:
        text += 'No bids yet\n'

    text += 'Current bid: ' + str(current_bid) + 'g\n'
    text += '-----\n'
    text += 'Send !help for commands'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})


def help():
    """
    Respond to the !help command
    """
    text = '[[ ' + bot_name + ' ]]\n'
    text += 'Send !bid ###g to bid on the current auction\n'
    text += 'Send !announce to see the current auction, high bidder, and current bid'
    scrolls.send({'msg': 'RoomChatMessage', 'roomName': room, 'text': text})

###
### ONE-OFF RESPONSES
###


def card_types(message):
    """
    Save the current master list of cards
    """
    global all_scrolls
    all_scrolls = message['cardTypes']


def library(message):
    """
    Save our current library
    """
    global library
    library = message['cards']
    populate_catalog()

###
### UTIL METHODS
###


def populate_catalog():
    """
    Fetches the latest prices from scrollspost and populates our catalog of rares and uncommons
    """
    global library
    global catalog
    prices_r = requests.get('http://api.scrollspost.com/v1/prices/1-day')
    prices = prices_r.json()

    for library_item in library:
        if library_item['tradable']:
            card = get_card(library_item['typeId'])

            if card['rarity'] == 0:
                continue
            for price_item in prices:
                if price_item['card_id'] == card['id']:
                    buy = price_item['price']['buy']
                    suggested = price_item['price']['suggested']
                    starting_bid = buy if buy > 0 else suggested
                    auction_item = (price_item['name'], starting_bid)
                    catalog.append(auction_item)

    random.shuffle(catalog)


def find_scroll_in_library(name):
    global all_scrolls
    global library
    for card_type in all_scrolls:
        if card_type['name'] == name:
            for library_item in library:
                if card_type['id'] == library_item['typeId'] and library_item['tradable']:
                    return library_item


def bot_profile_info(message):
    """
    Retrieve's the bot's own profile
    """
    global bot_profile
    bot_profile = message['profile']


def get_user(name):
    """
    retrieves a user's profile object by name
    """
    global profiles
    for user in profiles:
        if user['name'] == name:
            return user


def get_card(type_id):
    """
    retrieves a scroll object by type id
    """
    global all_scrolls
    for scroll in all_scrolls:
        if scroll['id'] == type_id:
            return scroll


def ban(bidder):
    """
    add a user to the ban list
    """
    global banned
    banned.update({bidder: time.time()})


def unban():
    """
    remove all users from the ban list
    whose time has been served
    """
    global banned
    banned_local = dict(banned)
    for bad_user, time_banned in banned_local.iteritems():
        if time.time() - time_banned > ban_threshold:
            banned.pop(bad_user)


def completed_auction_status():
    """
    The purpose of this function is to block the
    main auction loop until we are certain an auction
    has been completed or not
    """
    global completed_auction
    while (1):
        if completed_auction is True:
            completed_auction = None
            return True
        elif completed_auction is False:
            completed_auction = None
            return False
        else:
            time.sleep(1)

# init the scrolls client
scrolls = ScrollsSocketClient(email, password)

# subscribe to the SignIn event with function run()
scrolls.subscribe('SignIn', run)
scrolls.subscribe('ProfileInfo', bot_profile_info)

# login to the server
scrolls.login()
