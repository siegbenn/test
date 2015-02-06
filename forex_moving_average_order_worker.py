from globals import Globals
import time
import boto.sqs
from boto.sqs.message import Message
from forex_moving_average_functions import get_position
from forex_moving_average_functions import delete_position
from forex_moving_average_functions import create_order

account_id = Globals.account
token = Globals.token

# Create connection to SQS queue.
conn = boto.sqs.connect_to_region('us-east-1')
queue = conn.get_queue('forex_atr_orders')
messages = True

while messages == True:
	rs = queue.get_messages(message_attributes=['pair', 'units', 'side', 'stop'])
	if len(rs) == 1:
		m = rs[0]
		pair = m.message_attributes['pair']['string_value']
		units = int(m.message_attributes['units']['string_value'])
		side = m.message_attributes['side']['string_value']
		stop = int(m.message_attributes['stop']['string_value'])

		position = get_position(pair, account_id, token)

		current_position = position.pair
		current_side = position.side
		current_units = int(position.units)
		
		if current_side == side:
			queue.delete_message(m)
		else:
			delete_position(pair, account_id, token)
			time.sleep(0.5)
			create_order(pair, account_id, token, side, units, stop)
			queue.delete_message(m)
	else:
		messages = False

	time.sleep(0.5)
	
print "Done processing queue"