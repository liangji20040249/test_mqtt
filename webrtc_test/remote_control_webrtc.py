import asyncio
import json
import time
import cv2
import numpy as np
import paho.mqtt.client as mqtt
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole

# ================= 配置 =================
MQTT_BROKER = "broker.emqx.io"
TOPIC_SIGNAL_OUT = "liang/signal/c2r"  # 发给机器人的 Offer
TOPIC_SIGNAL_IN  = "liang/signal/r2c"  # 接收机器人的 Answer
TOPIC_CONTROL    = "liang/retail/cmd"

# ================= 全局变量 =================
current_frame = None  # 用于 UI 显示的最新帧
signal_queue = asyncio.Queue()

# ================= MQTT =================
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"✅ [控制端] MQTT连接成功，监听信令: {TOPIC_SIGNAL_IN}")
    client.subscribe(TOPIC_SIGNAL_IN)

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    if payload.get("type") == "answer":
        print("📩 [信令] 收到机器人的 Answer 名片")
        signal_queue.put_nowait(payload)

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, 1883, 60)
mqtt_client.loop_start()

# ================= WebRTC 协程逻辑 =================
async def consume_video(track):
    """从 WebRTC 轨道中不断取帧"""
    global current_frame
    while True:
        try:
            # 这一步是关键：从 UDP 管道中解码出一帧
            frame = await track.recv()
            
            # 转换为 OpenCV 格式 (YUV -> BGR)
            # aiortc 的 frame.to_ndarray 自动处理格式转换
            img = frame.to_ndarray(format="bgr24")
            current_frame = img
        except Exception as e:
            print(f"视频流中断: {e}")
            break

async def start_webrtc():
    pc = RTCPeerConnection()
    
    # 创建一个收发器 (Transceiver)，告诉对方我想收视频
    pc.addTransceiver("video", direction="recvonly")
    
    # 监听轨道事件：当对方视频流过来时触发
    @pc.on("track")
    def on_track(track):
        print("🎥 [WebRTC] 捕捉到视频流轨道！")
        # 启动一个后台任务去消费这个视频流
        asyncio.create_task(consume_video(track))

    # 1. 创建 Offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    
    # 2. 发送 Offer 给机器人
    payload = {"type": "offer", "sdp": pc.localDescription.sdp}
    mqtt_client.publish(TOPIC_SIGNAL_OUT, json.dumps(payload))
    print("📤 [信令] 发送 Offer，呼叫机器人...")
    
    # 3. 等待 Answer
    answer_json = await signal_queue.get()
    
    # 4. 设置远端描述
    answer = RTCSessionDescription(sdp=answer_json["sdp"], type=answer_json["type"])
    await pc.setRemoteDescription(answer)
    print("✅ [WebRTC] 握手完成，P2P 通道建立！")

# ================= 主线程 (UI Loop) =================
def main():
    # 启动 WebRTC 协程 (在后台运行)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(start_webrtc())
    
    # 为了让 asyncio 和 opencv 共存，我们手动 tick loop
    print("🎮 [控制台] 启动。点击窗口，WASD 控制...")
    
    try:
        while True:
            # 1. 手动驱动 asyncio 跑一点点 (非阻塞)
            loop.run_until_complete(asyncio.sleep(0.01))
            
            # 2. OpenCV 显示
            if current_frame is not None:
                cv2.imshow("Industrial Remote View", current_frame)
            else:
                # 没图的时候显示黑屏等待
                blank = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(blank, "Connecting...", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255))
                cv2.imshow("Industrial Remote View", blank)
            
            # 3. 键盘控制 (通过 MQTT 发送)
            key = cv2.waitKey(1) & 0xFF
            v, w = 0.0, 0.0
            send = False
            
            if key == 27: break
            elif key == ord('w'): v=0.5; send=True
            elif key == ord('s'): v=-0.5; send=True
            elif key == ord('a'): w=1.0; send=True
            elif key == ord('d'): w=-1.0; send=True
            elif key == ord('q'): v=0; w=0; send=True
            
            if send:
                cmd = {"v": v, "w": w, "ts": time.time()}
                mqtt_client.publish(TOPIC_CONTROL, json.dumps(cmd), qos=0)
                print(f"指令发送: {v}, {w}")
                
    except KeyboardInterrupt:
        pass
    finally:
        mqtt_client.loop_stop()

if __name__ == "__main__":
    main()