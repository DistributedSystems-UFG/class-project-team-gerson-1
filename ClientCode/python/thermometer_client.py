#from __future__ import print_function

import logging

import grpc
import iot_service_pb2
import iot_service_pb2_grpc

from const import *

def run():
    with grpc.insecure_channel(GRPC_SERVER+':'+GRPC_PORT) as channel:
        stub = iot_service_pb2_grpc.IoTServiceStub(channel)
        response = stub.GetDevices(iot_service_pb2.DeviceRequest())
        print(response)

if __name__ == '__main__':
    logging.basicConfig()
    run()
