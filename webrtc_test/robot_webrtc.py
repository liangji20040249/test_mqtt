import asyncio
import json
import time
import cv2
import numpy as np
import paho.mqtt.client as mqtt
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

# ================= 配置 =================
MQTT_BROKER = "broker.emqx.io"
TOPIC_SIGNAL_IN  = "liang/signal/c2r"  # 接收来自控制端的信令
TOPIC_SIGNAL_OUT = "liang/signal/r2c"  # 发送给控制端的信令
TOPIC_CONTROL    = "liang/retail/cmd"  # 控制指令

# ================= 1. 定义虚拟相机轨道 =================
class SimulatedCameraTrack(VideoStreamTrack):
    """
    这是一个符合 WebRTC 标准的视频源。
    架构优势：未来换成真实相机，只需替换读取逻辑，WebRTC 管道不用动。
    """
    def __init__(self):
        super().__init__()
        self.img = cv2.imread("test_view.jpg") # 请确保图片存在
        if self.img is None: raise Exception("找不到图片!")

    async def recv(self):
        # 模拟 30fps 的帧生成
        pts, time_base = await self.next_timestamp()
        
        # 绘图：打上高精度的流逝时间，证明是实时流
        frame = self.img.copy()
        timestamp = f"WebRTC Live: {time.time():.3f}"
        cv2.putText(frame, timestamp, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        # 转换为 WebRTC 需要的 VideoFrame
        new_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        new_frame.pts = pts
        new_frame.time_base = time_base
        return new_frame

# ================= 2. 全局变量 =================
pc = None # PeerConnection 对象
signal_queue = asyncio.Queue() # 用于从 MQTT 线程传递消息到 Async 循环

# ================= 3. MQTT 各种回调 =================
def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    print(f"✅ [机器人] MQTT连接成功，监听信令: {TOPIC_SIGNAL_IN}")
    client.subscribe(TOPIC_SIGNAL_IN)
    client.subscribe(TOPIC_CONTROL)

def on_mqtt_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    
    # 区分是控制指令 还是 WebRTC信令
    if msg.topic == TOPIC_CONTROL:
        # 处理控制 (实时性要求低，直接打印)
        print(f"🤖 [底盘驱动] V={payload.get('v')} W={payload.get('w')}")
    
    elif msg.topic == TOPIC_SIGNAL_IN:
        # WebRTC 信令放入队列，交给主线程处理
        if payload.get("type") == "offer":
            print("📩 [信令] 收到控制端的 Offer 名片")
            signal_queue.put_nowait(payload)

# ================= 4. WebRTC 核心逻辑 =================
async def run_robot(mqtt_client):
    global pc
    pc = RTCPeerConnection()
    
    # 挂载摄像头轨道
    pc.addTrack(SimulatedCameraTrack())
    
    # 等待控制端发来 Offer (呼叫)
    print("⏳ [WebRTC] 等待呼叫...")
    
    # 从队列取 Offer
    offer_json = await signal_queue.get()
    
    # 1. 设置远端描述 (读对方的名片)
    offer = RTCSessionDescription(sdp=offer_json["sdp"], type=offer_json["type"])
    await pc.setRemoteDescription(offer)
    
    # 2. 创建应答 (印自己的名片)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    # 3. 通过 MQTT 发回 Answer
    answer_payload = {"type": "answer", "sdp": pc.localDescription.sdp}
    mqtt_client.publish(TOPIC_SIGNAL_OUT, json.dumps(answer_payload))
    print("📤 [信令] 发送 Answer 名片，P2P 通道即将建立...")
    
    # 保持运行
    await asyncio.Future() # run forever

# ================= 主入口 =================
if __name__ == "__main__":
    # 启动 MQTT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_mqtt_connect
    client.on_message = on_mqtt_message
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()

    try:
        asyncio.run(run_robot(client))
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()