import time
import random
import json
import paho.mqtt.client as mqtt

# --- 配置 ---
BROKER = "broker.emqx.io"
PORT = 1883
TOPIC = "test/liang/command"
CLIENT_ID = f"mac_publisher_{random.randint(0, 1000)}"

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ [发送端] 就绪! (输入 q 退出)")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
client.on_connect = on_connect
client.connect(BROKER, PORT, 60)
client.loop_start()

time.sleep(1) # 等连接稳定

try:
    while True:
        msg = input("\n请输入指令 > ")
        if msg.lower() == 'q': break
        
        # 1. 封装数据包 (Payload)
        # 打入当前的发送时刻 T_send
        payload = {
            "msg": msg,
            "ts": time.time() 
        }
        
        # 2. 序列化为 JSON 字符串
        payload_str = json.dumps(payload)
        
        # 3. 发送
        client.publish(TOPIC, payload_str, qos=0)
        print(f"🚀 数据包已发出 (Size: {len(payload_str)} bytes)")

except KeyboardInterrupt:
    pass

client.loop_stop()
client.disconnect()
