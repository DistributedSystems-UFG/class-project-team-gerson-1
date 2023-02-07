from enum import Enum
import json
import time
from kafka import KafkaConsumer, KafkaProducer
from const import *
import threading

from concurrent import futures
import logging

import grpc
import iot_service_pb2
import iot_service_pb2_grpc

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
        
class IoTServer(iot_service_pb2_grpc.IoTServiceServicer):

    def SayTemperature(self, request, context):
        return iot_service_pb2.TemperatureReply(temperature=CURRENT_TEMPERATURE)

    def GetDevices(self, request, context):
        devices = []
        for device_id in TWIN_DEVICE_TABLE.keys():
            device = TWIN_DEVICE_TABLE[device_id]
            device_item = iot_service_pb2.DeviceItem(deviceId=device_id, state=device['state'])
            devices.append(device_item)
        return iot_service_pb2.DeviceReply(devices=devices)
    
    def BlinkLed(self, request, context):
        print ("Blinking deviceId: ", request.deviceId)
        print ("...with state ", request.state)

        if (request.deviceId in TWIN_DEVICE_TABLE.keys()):
            produce_led_command(request.deviceId, request.state) 
            return iot_service_pb2.LedReply()
        return iot_service_pb2.LedReply()

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    iot_service_pb2_grpc.add_IoTServiceServicer_to_server(IoTServer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    logging.basicConfig()

    devices_sync_thread = threading.Thread(target=consume_device_sync)
    devices_sync_thread.start()

    devices_temperature_thread = threading.Thread(target=consume_temperature)
    devices_temperature_thread.start()

    request_device_sync()

    serve()
