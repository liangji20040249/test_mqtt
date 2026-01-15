import time
import random
import json
import paho.mqtt.client as mqtt

# --- 配置 ---
BROKER = "broker.emqx.io"
PORT = 1883
TOPIC = "test/liang/command"
CLIENT_ID = f"mac_subscriber_{random.randint(0, 1000)}"

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ [接收端] 连接成功! 监听中...")
        client.subscribe(TOPIC)
    else:
        print(f"❌ 连接失败 code: {rc}")

def on_message(client, userdata, msg):
    # 1. 获取接收时刻 (Arrival Time)
    t_recv = time.time()
    
    try:
        # 2. 解析 Payload
        payload_str = msg.payload.decode()
        data = json.loads(payload_str)
        
        content = data.get("msg", "")
        t_send = data.get("ts", 0)
        
        # 3. 计算延迟 (秒 -> 毫秒)
        latency_ms = (t_recv - t_send) * 1000
        
        # 4. 打印结果
        print("-" * 40)
        print(f"📩 [收到消息] 内容: {content}")
        print(f"⏱️ [链路延迟] {latency_ms:.2f} ms")
        
        # 业务逻辑演示
        if content == "forward":
            print("   >>> 🤖 底盘前进")
            
    except json.JSONDecodeError:
        print(f"⚠️ 收到非JSON格式消息: {msg.payload}")

# --- 主程序 ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
client.on_connect = on_connect
client.on_message = on_message

print("[接收端] 连接 Broker: broker.emqx.io ...")
client.connect(BROKER, PORT, 60)

try:
    client.loop_forever()
except KeyboardInterrupt:
    pass
