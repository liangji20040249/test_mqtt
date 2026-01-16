import time
import json
import cv2
import numpy as np
import paho.mqtt.client as mqtt

# ================= 架构配置 =================
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883

TOPIC_CMD = "liang/retail/cmd_vel"   # 发送
TOPIC_IMG = "liang/retail/camera"    # 接收

CLIENT_ID = f"controller_mac_{int(time.time())}"

# 速度预设
SPEED_LINEAR = 0.5  # m/s
SPEED_ANGULAR = 1.0 # rad/s

# 全局变量：存储最新一帧图像
current_frame = None

# ================= MQTT 逻辑 =================
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ [控制台] 连接成功! 等待视频流...")
        client.subscribe(TOPIC_IMG)
    else:
        print(f"❌ 连接失败: {rc}")

def on_message(client, userdata, msg):
    global current_frame
    try:
        # 1. 接收二进制数据
        img_bytes = msg.payload
        
        # 2. 解码 (Bytes -> Numpy -> Image)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is not None:
            current_frame = img
            
    except Exception as e:
        print(f"⚠️ 图像解码失败: {e}")

# ================= 主程序 =================
if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message
    
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    print("🎮 [控制台] 启动成功！")
    print("操作指南: 点击视频窗口 -> 按 W/A/S/D 移动 -> 按 Q 停车 -> ESC 退出")

    # 创建一个黑色的初始画面
    current_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(current_frame, "Waiting for Video...", (100, 240), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    try:
        while True:
            # 1. 刷新显示图像
            if current_frame is not None:
                cv2.imshow("Remote View (Liang)", current_frame)
            
            # 2. 监听键盘 (每 50ms 刷新一次窗口)
            # waitKey 返回按键的 ASCII 码
            key = cv2.waitKey(50) & 0xFF
            
            # 3. 处理按键逻辑
            v, w = 0.0, 0.0
            should_send = False

            if key == 27: # ESC 键
                break
            elif key == ord('w'):
                v = SPEED_LINEAR
                should_send = True
            elif key == ord('s'):
                v = -SPEED_LINEAR
                should_send = True
            elif key == ord('a'):
                w = SPEED_ANGULAR
                should_send = True
            elif key == ord('d'):
                w = -SPEED_ANGULAR
                should_send = True
            elif key == ord('q'): # 急停
                v = 0.0
                w = 0.0
                should_send = True
            
            # 4. 发送指令 (仅当有按键时发送，避免空闲占用带宽)
            if should_send:
                payload = {
                    "v": v, 
                    "w": w,
                    "ts": time.time() # 打上发送时间戳
                }
                client.publish(TOPIC_CMD, json.dumps(payload), qos=0)
                print(f"📤 发送指令: v={v}, w={w}")

    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        cv2.destroyAllWindows()
        print("\n👋 控制台已退出")