import glob
from enum import Enum
import json
import math
import time
from kafka import KafkaProducer, KafkaConsumer
import RPi.GPIO as GPIO # Import Raspberry Pi GPIO library
import threading

from const import *

base_dir = '/sys/bus/w1/devices/'
device_folder = glob.glob(base_dir + '28*')[0]
device_file = device_folder + '/w1_slave'
last_reported = 0

# Initialize GPIO
GPIO.setwarnings(False) # Ignore warning for now
GPIO.setmode(GPIO.BOARD) # Use physical pin numbering
GPIO.setup(16, GPIO.OUT, initial=GPIO.LOW) # Set pin 16 to be an output pin and set initial value to low (off)
GPIO.setup(18, GPIO.OUT, initial=GPIO.LOW) # Idem for pin 18

def read_temp_raw():
    f = open(device_file, 'r')
    lines = f.readlines()
    f.close()
    return lines

def read_temp():
    lines = read_temp_raw()
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
        temp_f = temp_c * 9.0 / 5.0 + 32.0
        return temp_c, temp_f

class DeviceType(Enum):
    LED = "LED"
    SENSOR = "SENSOR"

class DeviceStatus(Enum):
    ON = "ON"
    OFF = "OFF"
    RUNNING = "RUNNING"

DEVICE_TABLE = {
    '1': {
        'name': 'LED Vermelho',
        'pin': 16,
        'state': DeviceStatus.OFF,
        'type': DeviceType.LED,
        'extra': { }
    },
    '2': {
        'name': 'LED Verde',
        'pin': 18,
        'state': DeviceStatus.OFF,
        'type': DeviceType.LED,
        'extra': { }
    },
    '3': {
        'name': 'Sensor de Temperatura',
        'pin': None,
        'state': DeviceStatus.OFF,
        'type': DeviceType.SENSOR,
        'extra': {
            'temperature': 'void'
        }
    }
}

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER+':'+KAFKA_PORT,
    security_protocol='SASL_SSL',
    sasl_mechanism='PLAIN',
    sasl_plain_username=KAFKA_USER,
    sasl_plain_password=KAFKA_PASSWORD 
)

def sync_all_devices():
    for device_id in DEVICE_TABLE.keys():
        sync_device(device_id)

def sync_device(device_id: str):
    message = json.dumps({
        'id': device_id,
        'name': DEVICE_TABLE[device_id]['name'],
        'state': DEVICE_TABLE[device_id]['state'].value,
        'type': DEVICE_TABLE[device_id]['type'].value,
        'extra': DEVICE_TABLE[device_id]['extra']
    })
    producer.send(DEVICE_SYNC_TOPIC, key=device_id.encode(), value = message.encode())
    producer.flush()
    print(f'Syncing device: {message}')

def new_consumer(topic):
    consumer = KafkaConsumer(
        bootstrap_servers=KAFKA_SERVER+':'+KAFKA_PORT,
        security_protocol='SASL_SSL',
        sasl_mechanism='PLAIN',
        sasl_plain_username=KAFKA_USER,
        sasl_plain_password=KAFKA_PASSWORD
    )
    consumer.subscribe(topics=(topic))
    return consumer

def consume_led_command():
    consumer = new_consumer(LED_COMMAND_TOPIC)
    for msg in consumer:
        print(f'Led command received: {msg.value.decode()}')
        message = json.loads(msg.value.decode())
        device_id = message['id']
        device = DEVICE_TABLE[device_id]
        device['state'] = DeviceStatus(message['state'])
        print(device)
        if device['type'] == DeviceType.LED:
            GPIO.output(device['pin'], GPIO.HIGH if device['state'] == DeviceStatus.ON else GPIO.LOW)
        device['state'] = DeviceStatus(message['state'])
        sync_device(device_id)

def consume_request_device_sync():
    consumer = new_consumer(REQUEST_DEVICE_SYNC_TOPIC)
    for msg in consumer:
        print(f'Received request device sync: {msg.value}')
        sync_all_devices()

thread_led_command = threading.Thread(target=consume_led_command)
thread_led_command.start()

thread_request_device_sync = threading.Thread(target=consume_request_device_sync)
thread_request_device_sync.start()

sync_all_devices()

while True:
    device = DEVICE_TABLE['3']
    if device['state'] == DeviceStatus.ON:
        (temp_c, temp_f) = read_temp()
        print(temp_c, temp_f)
        if (math.fabs(temp_c - last_reported) >= 0.1):
            last_reported = temp_c
            new_temperature = temp_c
            print(f'New temperature: {new_temperature}')
            device['extra']['temperature'] = str(new_temperature)
            message = json.dumps({ 'temperature': new_temperature })
            producer.send(NEW_TEMPERATURE_TOPIC, message.encode())
            sync_device('3')
    time.sleep(1)