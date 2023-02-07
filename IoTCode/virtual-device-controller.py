from enum import Enum
import json
import random
import time
from kafka import KafkaProducer, KafkaConsumer
import threading

from const import *

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
        'name': 'LED Azul',
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
        DEVICE_TABLE[device_id]['state'] = DeviceStatus(message['state'])
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
        new_temperature = random.uniform(25, 30)
        print(f'New temperature: {new_temperature}')
        device['extra']['temperature'] = str(new_temperature)
        message = json.dumps({ 'temperature': new_temperature })
        producer.send(NEW_TEMPERATURE_TOPIC, message.encode())
        sync_device('3')
    time.sleep(2)