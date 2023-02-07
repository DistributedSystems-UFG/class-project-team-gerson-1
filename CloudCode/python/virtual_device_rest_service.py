import json
import time
from kafka import KafkaConsumer, KafkaProducer
from const import *
import threading
from flask_cors import CORS

from flask import Flask

app = Flask(__name__)
CORS(app)

# Current temperature state
CURRENT_TEMPERATURE = 'void'

# Table representing twin leds and sensors
TWIN_DEVICE_TABLE = {}

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER+':'+KAFKA_PORT,
    security_protocol='SASL_SSL',
    sasl_mechanism='PLAIN',
    sasl_plain_username=KAFKA_USER,
    sasl_plain_password=KAFKA_PASSWORD 
)

def new_consumer(topics):
    consumer = KafkaConsumer(
        bootstrap_servers=KAFKA_SERVER+':'+KAFKA_PORT,
        security_protocol='SASL_SSL',
        sasl_mechanism='PLAIN',
        sasl_plain_username=KAFKA_USER,
        sasl_plain_password=KAFKA_PASSWORD
    )
    consumer.subscribe(topics=topics)
    return consumer

def consume_temperature():
    global CURRENT_TEMPERATURE
    consumer = new_consumer(NEW_TEMPERATURE_TOPIC)
    for msg in consumer:
        event = json.loads(msg.value.decode())
        print(f"Temperature event: {event}")
        CURRENT_TEMPERATURE = event['temperature']

def consume_device_sync():
    consumer = new_consumer(DEVICE_SYNC_TOPIC)
    for msg in consumer:
        event = json.loads(msg.value.decode())
        print(f"Device sync event: {event}")
        device_id = event['id']
        event.pop('id', None)
        TWIN_DEVICE_TABLE[device_id] = event

def request_device_sync():
    time.sleep(2)
    producer.send(REQUEST_DEVICE_SYNC_TOPIC, key='sync'.encode(), value='sync'.encode())

def produce_led_command(device_id: str, state: str):
    message = json.dumps({ 'id': device_id, 'state': state })
    producer.send(LED_COMMAND_TOPIC, key=device_id.encode(), value=message.encode())
        
class IotService():

    def say_temperature(self):
        return CURRENT_TEMPERATURE

    def get_devices(self):
        devices = []
        for device_id in TWIN_DEVICE_TABLE.keys():
            device = TWIN_DEVICE_TABLE[device_id]
            devices.append({ **device, 'id': device_id })
        return devices
    
    def blink_led(self, request):
        print ("Blinking deviceId: ", request.deviceId)
        print ("...with state ", request.state)

        if (request.deviceId in TWIN_DEVICE_TABLE.keys()):
            produce_led_command(request.deviceId, request.state)

def serve():
    iot_service = IotService()

    @app.get("/temperature")
    def get_temperature():
        print("Getting temperature")
        return {"temperature": iot_service.say_temperature()}
    
    @app.get("/devices")
    def get_devices():
        print("Getting temperature")
        return {"devices": iot_service.get_devices()}
    
    @app.patch("/blink/<deviceId>/<state>")
    def blink(deviceId, state):
        print("Getting temperature")
        produce_led_command(deviceId, state)
        return {"ok": True}
    
    app.run(host='0.0.0.0', port=8080, debug=True)

    
devices_sync_thread = threading.Thread(target=consume_device_sync)
devices_sync_thread.start()

devices_temperature_thread = threading.Thread(target=consume_temperature)
devices_temperature_thread.start()

request_device_sync()

serve()
    
    
