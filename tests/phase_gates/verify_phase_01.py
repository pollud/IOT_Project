import os
import sys
import subprocess

def install_requirements():
    req_file = os.path.join(os.path.dirname(__file__), '..', '..', 'requirements.txt')
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"])

def verify_phase_1():
    try:
        install_requirements()
    except Exception as e:
        print(f"Failed to install requirements: {e}")
        sys.exit(1)

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    
    try:
        import shared
    except ImportError as e:
        print(f"FAIL: Could not import shared: {e}")
        sys.exit(1)

    # Test round trip
    try:
        original = shared.BadgePositionEvent(badge_id="b1", x=1.5, y=2.5)
        json_str = shared.to_json(original)
        restored = shared.from_json(shared.BadgePositionEvent, json_str)
        
        assert original == restored, f"Mismatch: {original} != {restored}"
        
        # Test another
        original_env = shared.EnvironmentEvent(temperature=22.5, humidity=45.0)
        json_env = shared.to_json(original_env)
        restored_env = shared.from_json(shared.EnvironmentEvent, json_env)
        
        assert original_env == restored_env, "Mismatch on EnvironmentEvent"

    except Exception as e:
        print(f"FAIL: Serialization round-trip failed: {e}")
        sys.exit(1)
        
    print("PASS: Phase 1 verification passed")

if __name__ == '__main__':
    verify_phase_1()
