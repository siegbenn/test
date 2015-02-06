from globals import Globals
import requests
import json
import boto.dynamodb
import boto.sqs
import boto.ses
from boto.sqs.message import Message
from boto.dynamodb2.table import Table


# Object to hold each moving average tick.
class Moving_Average_Tick(object):

    def __init__( self, timestamp, pair, moving_average_1, moving_average_2, close, sentiment ,high_low, atr_dollar, atr, order_percent ):
        self.timestamp = timestamp
        self.pair = pair
        self.moving_average_1 = moving_average_1
        self.moving_average_2 = moving_average_2
        self.close = close
        self.sentiment = sentiment
        self.high_low = high_low
        self.atr_dollar = atr_dollar
        self.atr = atr
        self.order_percent = order_percent

# Object to hold account information.
class Account(object):
	def __init__( self, margin_used, margin_available, unrealized_pl, realized_pl, margin_rate, open_trades, open_orders, balance, account_id ):
   		self.margin_used = margin_used
		self.margin_available = margin_available
		self.unrealized_pl = unrealized_pl
		self.realized_pl = realized_pl
		self.margin_rate = margin_rate
		self.open_trades = open_trades
		self.open_orders = open_orders
		self.balance = balance
		self.account_id = account_id

# Object to hold price tick.
class Tick(object):

    def __init__( self, timestamp, pair, bid, ask, status ):
        self.timestamp = timestamp
        self.pair = pair
        self.bid = bid
        self.ask = ask
        self.status = status

# Object to hold price tick.
class Position(object):

    def __init__( self, pair, side, units ):
        self.pair = pair
        self.side = side
        self.units = units

# Create a Moving_Average_Tick with pair, length and ganularity.
def create_moving_average_tick ( pair, length1, length2, granularity, token ):
	
	# Send request to oanda and check for 200 response status code.
	# Add one extra day to length to account for the removal of an unfinished bars.
	response = requests.get('https://api-fxpractice.oanda.com/v1/candles?instrument=' + pair + '&count=' + str(length1 + 1) + '&candleFormat=bidask&granularity=' + granularity + '&dailyAlignment=0&alignmentTimezone=America%2FNew_York', headers = { 'Authorization': 'Bearer '+ token })
	status_code = response.status_code

	# ERROR CHECK: status_code.
	if status_code != 200:
		raise Exception('Request status code != 200.')

	# Convert the response to JSON and set variables used in moving average calculation.
	response_json = response.json()
	pair_candles = response_json['candles']

	# Check for an unfinished bar.
	if pair_candles[length1]['complete'] == False:

		# Remove the unfinished bar.
		del pair_candles[-1]
	else:

		# No unfinished bar. Remove the oldest bar so length = 200.
		del pair_candles[0]

	bar_count = len(pair_candles)

	# ERROR CHECK: pair_candles.
	if bar_count != length1:
		raise Exception('Request returned incorrect amount of bars.')

	# Calculate the moving average.
	bar_sum_1 = 0
	bar_sum_2 = 0
	tr_sum = 0
	tr_dollar = 0
	for i in range(0,bar_count):
		
		# Set TR variables.
		today_low = pair_candles[i]['lowAsk']
		today_high = pair_candles[i]['highAsk']
		yesterday_close = pair_candles[i-1]['closeAsk']
		today_close = (pair_candles[i]['closeBid'] + pair_candles[i]['closeAsk']) / 2

		# Get TR min and max.
		low = [today_low,yesterday_close]
		high = [today_high, yesterday_close]
		tr_min = min(low)
		tr_max = max(high)

		# Calculate TR.
		tr = (tr_max - tr_min) / today_close
		tr_dollar += (tr_max - tr_min)
		tr_sum += tr

		bar_sum_1 += today_close

	for i in range(bar_count-length2,bar_count):
		today_close = (pair_candles[i]['closeBid'] + pair_candles[i]['closeAsk']) / 2
		bar_sum_2 += today_close


	# Set the Moving_Average_Tick variables.
	timestamp = pair_candles[bar_count-1]['time']
	moving_average_1 = (bar_sum_1 / bar_count)
	moving_average_2 = (bar_sum_2/ length2)
	atr = tr_sum / bar_count
	atr_dollar = tr_dollar / bar_count
	close = (pair_candles[bar_count-1]['closeBid'] + pair_candles[bar_count-1]['closeAsk']) / 2
	sentiment = 'BULL'
	if moving_average_2 < moving_average_1:
		sentiment = 'BEAR'

	high_low = "no"
	high = -1
	low = 1000
	for i in range(bar_count-length2,bar_count):

		today_close = (pair_candles[i]['closeBid'] + pair_candles[i]['closeAsk']) / 2
		if today_close >= high:
			high = today_close
		if today_close <= low:
			low = today_close

		bar_sum_2 += today_close

	if high == close:
		high_low = "high"
	if low == close:
		high_low = "low"
	
	# Create the Moving_Average_Tick
	moving_average_tick = Moving_Average_Tick(timestamp,pair,moving_average_1,moving_average_2,close,sentiment, high_low, atr_dollar, atr, 0)

	# Return the Moving_Average_Tick.
	return moving_average_tick


# Get a full list of tradeable instruments for account.
def get_instrument_list ( account, token ):

	# Send request to oanda and check for 200 response status code.
	response = requests.get('https://api-fxpractice.oanda.com/v1/instruments?accountId=' + str(account), headers = { 'Authorization': 'Bearer ' + token })
	status_code = response.status_code

	# ERROR CHECK: status_code.
	if status_code != 200:
		raise Exception('Request status code != 200.')

	# Convert the response to JSON and populate instrument list.
	response_json = response.json()
	instruments_json = response_json['instruments']
	instrument_count = len(instruments_json)
	instruments = []
	for i in range(0,instrument_count):
		instruments.append(instruments_json[i]['instrument'])

	# Return the list of instrument names.
	return instruments


def save_moving_average_tick ( pair, timestamp, moving_average_1, moving_average_2, close, sentiment, high_low,atr_dollar, atr, order_percent):
	
	# Create DynamoDB connection.
	conn = boto.dynamodb.connect_to_region('us-east-1')
	table = conn.get_table('forex_atr_ticks')

	# Create DynamoDB tick item.
	tick = table.new_item(
		hash_key = pair,
		range_key = timestamp,
		attrs = { 'close': close, 'moving_average_1': moving_average_1, 'moving_average_2': moving_average_2, 'sentiment': sentiment, 'high_low': high_low , 'atr_dollar': atr_dollar, 'atr': atr, 'order_percent': order_percent}
	)

	# Save DynamoDB item.
	tick.put()


def create_queue_order ( pair, side, units, stop ):

	# Create connection to SQS queue.
	conn = boto.sqs.connect_to_region('us-east-1')
	queue = conn.get_queue('forex_atr_orders')

	# Set queue message.
	message = Message()
	message.set_body( pair + ' ' + side +  ' ' + str(units) )

	# Set queue message attributes.
	message.message_attributes = {
		"pair": {
			"data_type": "String",
			"string_value": pair
		},
		"side": {
			"data_type": "String",
			"string_value": side
		},
		"units": {
			"data_type": "Number",
			"string_value": str(units)
		},
		"stop": {
			"data_type": "Number",
			"string_value": str(stop)
		}
	}

	# Write message to queue.
	queue.write(message)

def get_moving_average_tick ( pair ):

	# Set the DynamoDB table.
	table = Table('forex_atr_ticks')

	# Query for latest moving_average_tick.
	ticks = table.query_2(
		pair__eq = pair,
		reverse = True,
		limit = 1
	)

	# Initialize Moving_Average_Tick variables.
	timestamp = ""
	pair = ""
	moving_average_1 = 0
	moving_average_2 = 0
	close = 0
	sentiment = ""
	high_low = ""
	atr_dollar = 0
	atr = 0
	order_percent = 0

	# Set the Moving_Average_Tick variables.
	for tick in ticks:
		timestamp = tick['timestamp']
		pair = tick['pair']
		moving_average_1 = tick['moving_average_1']
		moving_average_2 = tick['moving_average_2']
		close = tick['moving_average_close']
		sentiment = tick['sentiment']
		high_low = tick['high_low']
		atr_dollar = tick['atr_dollar']
		atr = tick['atr']
		order_percent = tick['order_percent']

	# Set the Moving_Average_Tick.
	atr_tick = Moving_Average_Tick(timestamp,pair,moving_average_1,moving_average_2,close,sentiment,high_low,atr_dollar,atr,order_percent)

	# Return the Moving_Average_Tick.
	return atr_tick

def get_pip ( pair ):

	# Set the DynamoDB table.
	table = Table('forex_instrument_pips')

	# Query for latest moving_average_tick.
	ticks = table.query_2(
		instrument__eq = pair,
		reverse = True,
		limit = 1
	)

	# Initialize Moving_Average_Tick variables.
	pair = ""
	pip = 0

	# Set the Moving_Average_Tick variables.
	for tick in ticks:
		pair = tick['pair']
		pip = tick['pip']

	# Return the Moving_Average_Tick.
	return pip

def get_account ( account, token ):
	
	# Send request to oanda and check for 200 response status code.
	response = requests.get('https://api-fxpractice.oanda.com/v1/accounts/' + str(account), headers = { 'Authorization': 'Bearer '+ token })
	status_code = response.status_code

	# ERROR CHECK: status_code.
	if status_code != 200:
		raise Exception('Request status code != 200.')

	# Convert the response to JSON and set account variables.
	
	response_json = response.json()
	margin_used = response_json['marginUsed']
	margin_available = response_json ['marginAvail']
	unrealized_pl = response_json['unrealizedPl']
	realized_pl = response_json['realizedPl']
	margin_rate = response_json['marginRate']
	open_trades = response_json['openTrades']
	open_orders = response_json['openOrders']
	balance = response_json['balance']
	account_id = response_json['accountId']

	# Set the Account.
	account = Account(margin_used,margin_available,unrealized_pl,realized_pl,margin_rate,open_trades,open_orders,balance,account_id)

	# Return the Account.
	return account

def get_current_price ( pair, token ):

	# Send request to oanda and check for 200 response status code.
	response = requests.get('https://api-fxpractice.oanda.com/v1/prices?instruments=' + pair, headers = { 'Authorization': 'Bearer '+ token })
	status_code = response.status_code

	# ERROR CHECK: status_code.
	if status_code != 200:
		raise Exception('Request status code != 200.')

	# Convert the response to JSON and set tick variables.
	response_json = response.json()
	timestamp = response_json['prices'][0]['time']
	pair = response_json['prices'][0]['instrument']
	bid = response_json['prices'][0]['bid']
	ask = response_json['prices'][0]['ask']
	if 'status' in response_json.keys():
		status = response_json['prices'][0]['status']
	else:
		status = 'open'

	# Set the Tick.
	tick = Tick(timestamp,pair,bid,ask,status)

	# Return the Tick.
	return tick

def send_email ( address, subject, message ):
	conn = boto.ses.connect_to_region('us-east-1')
	conn.send_email(
        'bennett.e.siegel@gmail.com',
        subject,
        message,
        [address]
    )

def create_order ( pair, account, token, side, units, stop):
	payload = {'instrument': pair, 'units': units, 'side': side,'type': 'market', 'trailingStop': stop}
	response = requests.post('https://api-fxpractice.oanda.com/v1/accounts/' + str(account) + '/orders', data = payload , headers = { 'Authorization': 'Bearer '+ token })
	status_code = response.status_code
	if status_code != 200:
		return False
	else:
		return True

def get_position ( pair, account, token ):
	# Send request to oanda and check for 200 response status code.
	response = requests.get('https://api-fxpractice.oanda.com/v1/accounts/' + str(account) + '/positions/' + pair, headers = { 'Authorization': 'Bearer '+ token })
	status_code = response.status_code
	
	response_json = response.json()
	# ERROR CHECK: status_code.
	if status_code != 200:
		position = Position(pair, 'none', 0)
		return position
	else:
		position = Position(pair, response_json['side'], response_json['units'])
		return position

def delete_position ( pair, account, token ):
	# Send request to oanda and check for 200 response status code.
	response = requests.delete('https://api-fxpractice.oanda.com/v1/accounts/' + str(account) + '/positions/' + pair, headers = { 'Authorization': 'Bearer '+ token })
	status_code = response.status_code
	if status_code != 200:
		return False
	else:
		return True

def save_account ( account_id, timestamp, margin_used, margin_available, unrealized_pl, realized_pl, margin_rate, open_trades, open_orders, balance ):
	
	# Create DynamoDB connection.
	conn = boto.dynamodb.connect_to_region('us-east-1')
	table = conn.get_table('forex_moving_average_account')

	# Create DynamoDB tick item.
	tick = table.new_item(
		hash_key = account_id,
		range_key = timestamp,
		attrs = { 'margin_used': margin_used, 'margin_available': margin_available, 'unrealized_pl': unrealized_pl, 'realized_pl': realized_pl, 'margin_rate': margin_rate, 'open_trades': open_trades, 'open_orders': open_orders, 'balance': balance}
	)

	# Save DynamoDB item.
	tick.put()