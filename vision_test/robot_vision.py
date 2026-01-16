import time
import json
import threading
import cv2
import numpy as np
import paho.mqtt.client as mqtt

# ================= 架构配置 =================
# 使用公共 Broker (生产环境请换成自建 EMQX)
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883

# 定义专属 Topic (加上你的名字防止冲突)
TOPIC_CMD = "liang/retail/cmd_vel"   # 接收：控制指令
TOPIC_IMG = "liang/retail/camera"    # 发送：图像流

# 客户端 ID
CLIENT_ID = f"robot_agent_{int(time.time())}"

# 模拟配置
IMAGE_SOURCE = "test_view.jpg"  # 本地图片路径
SEND_FPS = 10                   # 限制帧率 (MQTT传图建议不要超过15fps)

# ================= MQTT 回调逻辑 =================
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ [机器人] 上线成功! 正在监听: {TOPIC_CMD}")
        client.subscribe(TOPIC_CMD)
    else:
        print(f"❌ [机器人] 连接失败: {rc}")

def on_message(client, userdata, msg):
    """处理收到的控制指令"""
    try:
        payload = json.loads(msg.payload.decode())
        v = payload.get('v', 0.0)
        w = payload.get('w', 0.0)
        ts_sent = payload.get('ts', 0)
        
        # 计算指令延迟
        latency = (time.time() - ts_sent) * 1000
        
        # 模拟驱动底盘
        print(f"🤖 [底盘响应] 线速度: {v:>5.2f} | 角速度: {w:>5.2f} | 延迟: {latency:.1f}ms")
        
    except Exception as e:
        print(f"⚠️ 指令解析异常: {e}")

# ================= 视频推流线程 =================
def video_stream_task(client):
    """模拟摄像头采集并推流"""
    print("📷 [视觉] 摄像头推流线程启动...")
    
    # 读取底图
    base_frame = cv2.imread(IMAGE_SOURCE)
    if base_frame is not None:
        base_frame = cv2.resize(base_frame, (320, 240), interpolation=cv2.INTER_AREA)
    if base_frame is None:
        print(f"❌ 错误: 找不到 {IMAGE_SOURCE}，请在当前目录放一张图片！")
        return

    while True:
        loop_start = time.time()
        
        # 1. 模拟动态画面 (在图片上画时间戳)
        frame = base_frame.copy()
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        # 在左上角画红色的时间
        cv2.putText(frame, f"LIVE: {timestamp}", (20, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        
        # 2. 图像压缩 (关键！必须压缩成 JPEG)
        # 质量设为 50，平衡画质和带宽
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
        img_bytes = buffer.tobytes()
        
        # 3. 发送数据
        # QoS=0: 视频流允许丢包，追求实时性
        client.publish(TOPIC_IMG, img_bytes, qos=0)
        
        # 4. 帧率控制
        process_time = time.time() - loop_start
        wait_time = max(0, (1.0 / SEND_FPS) - process_time)
        time.sleep(wait_time)

# ================= 主程序 =================
if __name__ == "__main__":
    # 初始化 MQTT 客户端
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message
    
    print(f"[系统] 正在连接服务器 {MQTT_BROKER}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    
    # 启动后台线程处理 MQTT 网络收发
    client.loop_start()
    
    # 在主线程中启动视频推流 (也可以单独开线程，这里简化处理)
    try:
        video_stream_task(client)
    except KeyboardInterrupt:
        pass
    
    print("\n[系统] 机器人下线")
    client.loop_stop()
    client.disconnect()