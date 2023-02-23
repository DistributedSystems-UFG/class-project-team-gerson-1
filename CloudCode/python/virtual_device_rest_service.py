from datetime import datetime  
from datetime import timedelta
from functools import wraps  
import json
import time
from kafka import KafkaConsumer, KafkaProducer
from const import *
import threading
from flask_cors import CORS
import pymongo
from bson.objectid import ObjectId

from flask import Flask, request

import jwt

client = pymongo.MongoClient(MONGO_URL)
db = client.iot

app = Flask(__name__)
CORS(app)

# Current temperature state
CURRENT_TEMPERATURE = 'void'

# Table representing twin leds and sensors
TWIN_DEVICE_TABLE = {}

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization']
        if not token:
            return { 'message' : 'Authorization token is missing' }, 401

        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except:
            return { 'message' : 'Token is invalid' }, 401

        return f(data['iss'], *args, **kwargs)
  
    return decorated

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
        db.temperatures.insert_one({ "temperature": event['temperature'], "created_at": datetime.now()})
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

    def device_allowed(self, device_id, user_id):
        user = db.users.find_one({ "_id": ObjectId(user_id) })
        if user == None:
            return False
        return int(device_id) in user['devices_allowed']
    
    def get_all_temperatures(self, user_id):
        if not self.device_allowed("3", user_id):
            return { "message": "Device unauthorized" }, 403
        result = db.temperatures.find({ 
            'created_at': {
                '$gte': datetime.now() - timedelta(seconds=120), '$lt': datetime.now()
            }
        })
        temperatures = []
        for temp in result:
            temperatures.append({ "temperature": temp["temperature"], "created_at": str(temp["created_at"]) })
        return { "temperatures": temperatures }, 200

    def say_temperature(self, user_id):
        if not self.device_allowed("3", user_id):
            return { "message": "Device unauthorized" }, 403
        return { "temperature": CURRENT_TEMPERATURE }, 200

    def get_devices(self, user_id):
        user = db.users.find_one({ "_id": ObjectId(user_id) })

        if user == None:
            return []

        devices = []
        for device_id in user['devices_allowed']:
            if str(device_id) in TWIN_DEVICE_TABLE.keys():
                device = TWIN_DEVICE_TABLE[str(device_id)]
                devices.append({ **device, 'id': device_id })
        return devices
    
    def blink_led(self, user_id, device_id, state):
        if not self.device_allowed(device_id, user_id):
            return { "message": "Device unauthorized" }, 403

        if (device_id in TWIN_DEVICE_TABLE.keys()):
            produce_led_command(device_id, state)
            return { "state": state }, 204
        else:
            return { "message": "Device not synced" }, 422
    
    def me(self, user_id):
        user = db.users.find_one({ "_id": ObjectId(user_id) })
        if user == None:
            return { "message": "User not found" }, 404
        return { 'name': user['name'], 'email': user['email']}, 200
    
    def login(self, request):
        user = db.users.find_one({ "email": request['email'] })
        if user == None:
            return { "message": "User not found" }, 401

        if user['password'] == request['password']:
            token_payload = {
                "exp": datetime.now() + timedelta(days=2),
                "iss": str(user['_id'])
            }
            encoded_jwt = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
            return { "token": encoded_jwt }, 200

        return { "message": "Incorrect password" }, 401

def serve():
    iot_service = IotService()

    @app.get("/temperature")
    @token_required
    def get_temperature(user_id):
        print("Getting temperature")
        return iot_service.say_temperature(user_id)
    
    @app.get("/temperatures")
    @token_required
    def get_temperatures(user_id):
        print("Getting last temperatures")
        return iot_service.get_all_temperatures(user_id)
    
    @app.get("/devices")
    @token_required
    def get_devices(user_id):
        print("Getting all allowed devices")
        return {"devices": iot_service.get_devices(user_id)}
    
    @app.patch("/blink/<device_id>/<state>")
    @token_required
    def blink(user_id, device_id, state):
        return iot_service.blink_led(user_id, device_id, state)
    
    @app.post("/auth/login")
    def login():
        return iot_service.login(request.get_json())
    
    @app.get("/auth/me")
    @token_required
    def me(user_id):
        return iot_service.me(user_id)

    app.run(host='0.0.0.0', port=8080, debug=True)

    
devices_sync_thread = threading.Thread(target=consume_device_sync)
devices_sync_thread.start()

devices_temperature_thread = threading.Thread(target=consume_temperature)
devices_temperature_thread.start()

request_device_sync()

serve()
    
    
