import os
import sys
import subprocess
import time

def install_requirements():
    req_file = os.path.join(os.path.dirname(__file__), '..', '..', 'requirements.txt')
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"])

def verify_phase_2():
    try:
        install_requirements()
    except Exception as e:
        print(f"Failed to install requirements: {e}")
        sys.exit(1)

    import paho.mqtt.client as mqtt

    # 1. Bring up the mosquitto container
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    
    print("Bringing up docker-compose...")
    try:
        # For mac we might need docker compose (v2) instead of docker-compose
        subprocess.check_call(["docker", "compose", "up", "-d"], cwd=project_dir)
    except Exception as e:
        try:
            subprocess.check_call(["docker-compose", "up", "-d"], cwd=project_dir)
        except Exception as e2:
            print(f"FAIL: Failed to start docker-compose: {e2}")
            sys.exit(1)
            
    time.sleep(2) # Wait for broker to initialize

    # 2. Test round-trip
    message_received = False

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe("scratch/test")
            client.publish("scratch/test", "hello world")
        else:
            print(f"Failed to connect to Mosquitto, return code {rc}")

    def on_message(client, userdata, msg):
        nonlocal message_received
        if msg.topic == "scratch/test" and msg.payload.decode() == "hello world":
            message_received = True
            client.disconnect()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect("localhost", 1883, 60)
        
        # Loop for a short time to process callbacks
        start_time = time.time()
        while not message_received and time.time() - start_time < 5:
            client.loop(timeout=0.1)
            
    except Exception as e:
        print(f"FAIL: MQTT connection error: {e}")
        sys.exit(1)
        
    if not message_received:
        print("FAIL: Mosquitto round-trip failed (no message received).")
        sys.exit(1)

    print("PASS: Phase 2 verification passed")

if __name__ == '__main__':
    verify_phase_2()
