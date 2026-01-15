import time
import json
import threading
import struct
import platform  # 引入平台检测库
import paho.mqtt.client as mqtt

# 尝试导入 python-can，如果没有安装则提示
try:
    import can
except ImportError:
    print("请先运行: pip install python-can")
    exit()

# ================= 配置区域 =================
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
MQTT_TOPIC_CMD = "agilex/tracer/cmd_vel"
MQTT_ID = "tracer_robot_mac_sim" # 改个名字避免冲突

# ================= 驱动层 (自动适配 Mac/Linux) =================
class TracerDriver:
    def __init__(self, channel='can0', bitrate=500000):
        self.os_type = platform.system()
        self.bus = None
        
        print(f"[System] 检测到当前操作系统: {self.os_type}")

        try:
            if self.os_type == 'Linux':
                # 生产环境：使用 SocketCAN
                self.bus = can.interface.Bus(channel=channel, bustype='socketcan', bitrate=bitrate)
                print(f"[Driver] Linux SocketCAN initialized on {channel}")
            else:
                # 开发环境 (Mac/Win)：使用 Virtual 虚拟总线
                # 这种模式下，数据只会在内存里转圈，不会报错，适合调试逻辑
                self.bus = can.interface.Bus(channel='virtual_channel', bustype='virtual')
                print(f"[Driver] Mac/Win Virtual CAN initialized (模拟模式)")
            
            # 发送使能指令
            self.enable_control()
            
        except Exception as e:
            print(f"[Driver] ⚠️ CAN Init Warning: {e}")
            print("[Driver] 将运行在纯模拟模式 (无 CAN 对象)")
            self.bus = None

    def enable_control(self):
        if not self.bus: return
        msg = can.Message(arbitration_id=0x421, data=[0x01, 0, 0, 0, 0, 0, 0, 0], is_extended_id=False)
        try:
            self.bus.send(msg)
            print("[Driver] >> 发送使能帧: ID=0x421 Data=01... (Mac上只显示不真发)")
        except can.CanError as e:
            print(f"[Driver] Enable Failed: {e}")

    def send_motion_command(self, linear_x, angular_z):
        # 1. 限制幅度
        linear_x = max(-1.5, min(1.5, linear_x))
        angular_z = max(-1.0, min(1.0, angular_z))

        # 2. 协议打包
        v_mm_s = int(linear_x * 1000)
        w_mrad_s = int(angular_z * 1000)
        payload = struct.pack('>hh', v_mm_s, w_mrad_s) + b'\x00\x00\x00\x00'

        # 3. 发送
        if self.bus:
            msg = can.Message(arbitration_id=0x111, data=payload, is_extended_id=False)
            try:
                self.bus.send(msg)
                # 打印出来方便你在 Mac 上看到效果
                print(f"[Driver] >> CAN发送: V={linear_x} m/s, W={angular_z} rad/s")
            except can.CanError:
                print("[Driver] Send Error")
        else:
            print(f"[Mock] 虚拟驱动执行: V={linear_x}, W={angular_z}")

    def stop(self):
        self.send_motion_command(0, 0)

# ================= 业务逻辑 =================
driver = TracerDriver()
last_cmd_time = time.time()

# 修复 DeprecationWarning: 使用 VERSION2
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ [MQTT] 连接成功! 正在监听: {MQTT_TOPIC_CMD}")
        client.subscribe(MQTT_TOPIC_CMD)
    else:
        print(f"❌ 连接失败 code: {rc}")

def on_message(client, userdata, msg):
    global last_cmd_time
    try:
        payload = json.loads(msg.payload.decode())
        v = float(payload.get('v', 0.0))
        w = float(payload.get('w', 0.0))
        
        driver.send_motion_command(v, w)
        last_cmd_time = time.time()
        
    except Exception as e:
        print(f"[MQTT] Error: {e}")

def watchdog_task():
    while True:
        if time.time() - last_cmd_time > 0.5:
            # print("[Watchdog] 信号超时，停车...") # 刷屏太快先注释掉
            driver.stop()
        time.sleep(0.1)

# ================= 主程序 =================
if __name__ == "__main__":
    t = threading.Thread(target=watchdog_task)
    t.daemon = True
    t.start()

    # 修复 Warning: 显式指定 API 版本
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_ID)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[System] Connecting to {MQTT_BROKER}...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n程序退出")
    except Exception as e:
        print(f"连接错误: {e}")
