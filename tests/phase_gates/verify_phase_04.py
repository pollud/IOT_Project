import os
import sys
import subprocess
import time

def install_requirements():
    req_file = os.path.join(os.path.dirname(__file__), '..', '..', 'requirements.txt')
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"])

def verify_phase_4():
    install_requirements()
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    
    from shared.mqtt import MQTTClient
    
    print("Testing MQTT Client...")
    
    lwt_received = False
    reconnect_received = False
    
    def listener_on_message(topic, payload):
        nonlocal lwt_received, reconnect_received
        if topic == "system/lwt":
            lwt_received = True
        elif topic == "test/reconnect":
            reconnect_received = True

    listener = MQTTClient("listener", broker="localhost")
    listener.on_message_callback = listener_on_message
    listener.start()
    
    while not listener.connected:
        time.sleep(0.1)
        
    listener.subscribe("system/lwt")
    listener.subscribe("test/reconnect")
    
    # Test LWT by running a subprocess that dies
    lwt_script = """
import sys, time
sys.path.insert(0, '.')
from shared.mqtt import MQTTClient
client = MQTTClient("doomed", broker="localhost", lwt_topic="system/lwt", lwt_payload="dead")
client.start()
while not client.connected:
    time.sleep(0.1)
print("Doomed client connected")
sys.stdout.flush()
# Hard crash
import os
os._exit(1)
    """
    with open("doomed.py", "w") as f:
        f.write(lwt_script)
        
    subprocess.run([sys.executable, "doomed.py"])
    os.remove("doomed.py")
    
    # wait for LWT
    start = time.time()
    while not lwt_received and time.time() - start < 3:
        time.sleep(0.1)
        
    if not lwt_received:
        print("FAIL: LWT message was not received.")
        sys.exit(1)
    print("LWT test passed.")
    
    # Test reconnect by bouncing the broker
    test_client = MQTTClient("test_reconnect", broker="localhost")
    test_client.start()
    while not test_client.connected:
        time.sleep(0.1)
        
    print("Bouncing mosquitto container...")
    subprocess.run(["docker", "stop", "iotproject-mosquitto-1"], stdout=subprocess.DEVNULL)
    time.sleep(2)
    subprocess.run(["docker", "start", "iotproject-mosquitto-1"], stdout=subprocess.DEVNULL)
    
    # Wait for reconnect
    start = time.time()
    while not test_client.connected and time.time() - start < 10:
        time.sleep(0.5)
        
    if not test_client.connected:
        print("FAIL: Client did not reconnect.")
        sys.exit(1)
        
    # Test publish after reconnect
    test_client.publish("test/reconnect", "hello again")
    start = time.time()
    while not reconnect_received and time.time() - start < 3:
        time.sleep(0.1)
        
    if not reconnect_received:
        print("FAIL: Reconnected client could not publish.")
        sys.exit(1)
        
    listener.stop()
    test_client.stop()
    
    print("PASS: Phase 4 verification passed")

if __name__ == '__main__':
    verify_phase_4()
