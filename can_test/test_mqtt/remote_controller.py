import sys
import tty
import termios
import json
import paho.mqtt.client as mqtt

# 配置
MQTT_BROKER = "broker.emqx.io"
MQTT_TOPIC = "agilex/tracer/cmd_vel"

# TRACER 推荐速度
LINEAR_STEP = 0.4  # m/s
ANGULAR_STEP = 0.5 # rad/s

def get_key():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def main():
    client = mqtt.Client()
    client.connect(MQTT_BROKER, 1883, 60)
    
    print("=== TRACER Remote Control ===")
    print("WASD控制，Q停止，E退出")
    
    v, w = 0.0, 0.0
    
    try:
        while True:
            key = get_key()
            if key == 'w': v = LINEAR_STEP; w = 0
            elif key == 's': v = -LINEAR_STEP; w = 0
            elif key == 'a': v = 0; w = ANGULAR_STEP
            elif key == 'd': v = 0; w = -ANGULAR_STEP
            elif key == 'q': v = 0; w = 0
            elif key == 'e': break
            
            # 发送指令
            payload = json.dumps({'v': v, 'w': w})
            client.publish(MQTT_TOPIC, payload, qos=0)
            print(f"\rCMD: v={v}, w={w}    ", end="")
            
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(MQTT_TOPIC, json.dumps({'v': 0, 'w': 0}))
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, termios.tcgetattr(sys.stdin))

if __name__ == "__main__":
    main()
