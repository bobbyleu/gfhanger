import asyncio
import json

SEQUENCE_NUMBER = 0


class GfClient:
    def __init__(self, host, port, max_retries=3):
        self.host = host
        self.port = port
        self.recv_buffer = b""
        self.login_event = asyncio.Event()
        self.control_event = asyncio.Event()
        self.last_sent_type = None
        self.response_received = asyncio.Event()
        self.last_operation = None
        self.receive_task = None
        self.login_successful = False
        self.last_on_home_info = {}
        self.devices_info = []
        self.on_device_status_count = 0
        self.operation_success = False
        self.has_printed_login_success = False
        self.should_exit = False
        self.max_retries = max_retries
        # 新增变量，用于判断服务器连接是否断开
        self.is_connection_closed = False

    async def connect(self):
        if self.receive_task and not self.receive_task.done():
            return True  # 已经连接，直接返回
        retries = 0
        while retries < self.max_retries:
            try:
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                self._log_info(f"已连接到服务器 {self.host}:{self.port}")
                self.receive_task = asyncio.create_task(self.receive_messages())
                self.is_connection_closed = False  # 连接成功，将连接断开标志置为 False
                return True
            except ConnectionError as e:
                self._log_error(f"连接服务器失败: {e}, 重试第 {retries + 1} 次")
                retries += 1
        self._log_error("达到最大重试次数，连接失败")
        self._exit_program()
        self.is_connection_closed = True  # 连接失败，将连接断开标志置为 True
        return False

    def close(self):
        if self.receive_task:
            self.receive_task.cancel()
        if self.writer:
            self.writer.close()
        self._log_info("连接已关闭")
        self._exit_program()
        self.is_connection_closed = True  # 关闭连接，将连接断开标志置为 True

    async def send_message(self, hex_str, operation=None, retries=0):
        if self.is_connection_closed:
            if not await self.connect():
                return
        try:
            message_bytes = bytes.fromhex(hex_str)
            self.writer.write(message_bytes)
            await self.writer.drain()
            self.last_sent_type = hex_str[:4]
            self.response_received.clear()
            self.last_operation = operation
            # self._log_info(f"发送: {hex_str}")
        except ValueError as e:
            self._log_error(f"无效的十六进制消息: {hex_str}")
        except ConnectionError as e:
            if retries < self.max_retries:
                self._log_error(f"发送消息时连接错误: {e}, 尝试重新连接并再次发送")
                if await self.connect():
                    await self.send_message(hex_str, operation, retries + 1)
            else:
                self._log_error("达到最大重试次数，发送消息失败")
                self._exit_program()

    async def receive_messages(self):
        incomplete_message = b""
        while not self.should_exit:
            try:
                if self.is_connection_closed:
                    break
                data = await self.reader.read(4096)
                if not data:
                    self._log_info("服务器断开连接")
                    self.is_connection_closed = True  # 服务器断开连接，将连接断开标志置为 True
                    break
                self.recv_buffer += data
                # self._log_info(f"原始接收: {self.recv_buffer.hex()}")
                while len(self.recv_buffer) > 0:
                    if len(self.recv_buffer) < 4:
                        incomplete_message += self.recv_buffer
                        self.recv_buffer = b""
                        break

                    data_type_hex = self.recv_buffer[:2].hex()
                    if data_type_hex in ["0100", "0300", "0400"]:
                        if incomplete_message:
                            self.recv_buffer = incomplete_message + self.recv_buffer
                            incomplete_message = b""

                        length_hex = self.recv_buffer[2:4].hex()
                        data_length = int(length_hex, 16)
                        total_length = 4 + data_length
                        if len(self.recv_buffer) >= total_length:
                            message = self.recv_buffer[:total_length]
                            if not self.is_connection_closed:
                                self.process_complete_message(message)
                            self.recv_buffer = self.recv_buffer[total_length:]
                            self.response_received.set()
                    else:
                        incomplete_message += self.recv_buffer[:1]
                        self.recv_buffer = self.recv_buffer[1:]

            except Exception as e:
                self._log_error(f"接收消息出错: {str(e)}")

        if incomplete_message and not self.is_connection_closed:
            self.process_complete_message(incomplete_message)

    def process_complete_message(self, message):
        data_type = message[:2].hex()
        if data_type == "0300":
            # self._log_info(f"收到 data_type 为 0300 的消息，原始数据: {message.hex()}")
            return

        length_hex = message[2:4].hex()
        data_length = 4 + int(length_hex, 16)
        content = message[4:data_length]
        if data_type == "0400":
            content = message[6:data_length]

        try:
            content_str = content.decode('utf-8')
            if content_str.strip():
                index_dict = content_str.find('{')
                index_list = content_str.find('[')

                if index_dict != -1 or index_list != -1:
                    if index_dict == -1:
                        start_index = index_list
                    elif index_list == -1:
                        start_index = index_dict
                    else:
                        start_index = min(index_dict, index_list)

                    method = content_str[:start_index]
                    json_str = content_str[start_index:]
                    try:
                        parsed_content = json.loads(json_str)
                        # if method in ["onHomeInfo", "onLoginInfoEnd", "onDeviceStatusData"]:
                        #     self._log_info(f"解析成功: {data_type} 消息解析结果 - 方法: {method}, 内容: {parsed_content}")

                        if method == "onHomeInfo":
                            self._process_on_home_info(parsed_content)
                        elif method == "onLoginInfoEnd":
                            self._process_on_login_info_end(parsed_content)
                        elif method == "onDeviceStatusData":
                            self._process_on_device_status_data(parsed_content)

                        if data_type == "0400" and len(message) >= 5 and message[4] == 0x04:
                            self._process_operation_feedback(parsed_content)

                    except json.JSONDecodeError:
                        self._log_error(f"消息内容不是有效的 JSON 格式: {json_str}")
                else:
                    self._log_error(f"未找到有效的 JSON 起始标识，内容为: {content_str}")
            else:
                self._log_error("接收到的消息内容为空，无法解析")
        except UnicodeDecodeError:
            self._log_error(f"消息解码错误: 原始数据: {content.hex()}")

    def _process_on_home_info(self, parsed_content):
        self.last_on_home_info = parsed_content
        self.devices_info = []
        homes = parsed_content.get('homes', [])
        for home in homes:
            layers = home.get('layers', [])
            for layer in layers:
                home_grids = layer.get('homeGrids', [])
                for home_grid in home_grids:
                    devices = home_grid.get('devices', [])
                    for device in devices:
                        e_name = device.get('e_name')
                        _id = device.get('_id')
                        status = device.get('props', {}).get('status')
                        position = device.get('props', {}).get('position')
                        if e_name and _id and status is not None and position is not None:
                            self.devices_info.append({
                                'e_name': e_name,
                                '_id': _id,
                                'status': status,
                                'position': position
                            })
        if not self.devices_info:
            self._log_error("未从 onHomeInfo 中获取到设备信息，关闭连接并退出程序")
            self.close()

    def _process_on_login_info_end(self, parsed_content):
        code = parsed_content.get('code')
        if code == 200:
            if not self.has_printed_login_success:
                self._log_info("登录成功")
                self.has_printed_login_success = True
            self.login_successful = True
            self.login_event.set()
        else:
            self._log_error("登录失败")
            self.close()

    def _process_on_device_status_data(self, parsed_content):
        device = parsed_content.get('devices', [])[0]
        if device:
            e_name = device.get('e_name')
            _id = device.get('_id')
            status = device.get('props', {}).get('status')
            position = device.get('props', {}).get('position')
            self._log_info(f"设备状态 - e_name: {e_name}, _id: {_id}, status: {status}, position: {position}")
            for i, dev in enumerate(self.devices_info):
                if dev['_id'] == _id:
                    self.devices_info[i]['status'] = status
                    self.devices_info[i]['position'] = position
                    break
            if self.last_operation == 'remote_control' and self.operation_success:
                self.control_event.set()  #此功能会导致不再接收设备操作结果信息，后续再研究如何处理
                self._log_info("设备操作成功")
        else:
            self._log_info("未获取到设备状态更新信息")

    def _process_operation_feedback(self, parsed_content):
        if self.is_connection_closed:
            return
        code = parsed_content.get('code')
        codetxt = parsed_content.get('codetxt')
        self._log_info(f"操作反馈信息 - code: {code}, codetxt: {codetxt}")
        self.operation_success = code == 200
        if code != 200:
            self._log_error("操作返回码非 200，关闭连接并退出程序")
            self.close()
        elif self.last_operation == 'remote_control' and not self.operation_success:
            self._log_info("设备操作失败")

    def generate_hex_message(self, method_name, data, is_operation_command=False):
        global SEQUENCE_NUMBER
        SEQUENCE_NUMBER += 1
        sequence_hex = format(SEQUENCE_NUMBER, '04X')

        method_hex = method_name.encode('utf-8').hex().upper()
        json_hex = json.dumps(data, separators=(',', ':')).encode('utf-8').hex().upper()

        middle_part = "20" if not is_operation_command else "1F"
        full_content_hex = sequence_hex + middle_part + method_hex + json_hex
        length_hex = format(len(full_content_hex) // 2, '04X')

        return f"0400{length_hex}{full_content_hex}"

    async def login(self, mobile, password, clientid):
        if not await self.connect():
            return False
        await self.send_message(
            "0100003B7B22737973223A7B2276657273696F6E223A22302E332E30222C2274797065223A22756E6974792D736F636B6574227D2C2275736572223A7B7D7D")
        await self.response_received.wait()

        await self.send_message("02000000")
        await self.response_received.wait()

        method_name = "connector.userEntryHandler.login"
        login_data = {
            "mobile": mobile,
            "password": password,
            "packageName": "ypr",
            "clientid": clientid
        }

        hex_message = self.generate_hex_message(method_name, login_data)
        await self.send_message(hex_message, operation='login')
        await self.response_received.wait()

        try:
            await asyncio.wait_for(self.login_event.wait(), timeout=10)
            return self.login_successful
        except asyncio.TimeoutError:
            self._log_error("登录超时，请检查网络或服务器状态。")
            self.close()
            return False

    async def remote_control(self, mobile, password, clientid, deviceId, operation_code, retries=0):
        operation_mapping = {
            1: "putDown",
            2: "raiseUp",
            3: "stop"
        }
        name = operation_mapping.get(operation_code)

        # 判断连接是否断开
        if self.is_connection_closed:
            self._log_info("连接已断开，尝试重新连接并登录...")
            if not await self.login(mobile, password, clientid):
                return False

        # 重置事件
        self.control_event.clear()
        self.on_device_status_count = 0
        self.operation_success = False

        method_name = "main.userHandler.remoteControll"
        control_data = {
            "deviceId": deviceId,
            "props": [{"name": name, "method": "set", "value": None}]
        }

        hex_message = self.generate_hex_message(method_name, control_data, is_operation_command=True)
        await self.send_message(hex_message, operation='remote_control')

        try:
            await asyncio.wait_for(self.control_event.wait(), timeout=10)
            return True
        except asyncio.TimeoutError:
            if retries < self.max_retries:
                self._log_error(f"操作失败：未收到位置反馈，重试第 {retries + 1} 次")
                return await self.remote_control(mobile, password, clientid, deviceId, operation_code, retries + 1)
            else:
                self._log_error("达到最大重试次数，操作失败")
                return False

    def _log_info(self, message):
        print(f"[注意] {message}")

    def _log_error(self, message):
        print(f"[错误] {message}")

    def _exit_program(self):
        self.should_exit = True