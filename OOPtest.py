import ctypes
import os
import sys

os.add_dll_directory(os.path.dirname(os.path.realpath(__file__)))
import threading
import time

import hid
import pystray
from PIL import Image, ImageDraw, ImageFont


class WLMouse:
    def __init__(self, vid):
        self.vid = 0x36A7
        self.last_nonzero_level = 1
        self.name = 'WLmouse'

        devices = hid.enumerate(vid)
        if not devices:
            raise Exception('No WLmouse devices found.')

        for device in devices:
            try:
                mouse = hid.Device(path=device['path'])
                print('Mouse found')
                try:
                    self.mouse = mouse
                    self.get_battery()
                    break
                except Exception as e:
                    print(e)
                    self.mouse = None
                    mouse.close()
                    continue

            except hid.HIDException as e:
                print(f'Cannot open with path: {e}')
                continue

        if self.mouse is None:
            raise Exception('No usable Wlmouse HID interface found.')

    def get_battery(self):
        command_buffer = [0x00] * 65  # got this command buffer from https://gm.wlmouse.gg/#/project/items
        command_buffer[3] = 0x2  # searched by 'getReport', 'getBat' in devtools (js)
        command_buffer[4] = 0x2  # this exact command buffer needed to get battery life response
        command_buffer[6] = 0x83
        write_result = self.mouse.send_feature_report(bytes(command_buffer))
        print(f'Отправлено байт: {write_result}')
        time.sleep(0.1)
        read_result = self.mouse.get_feature_report(0x0, 65)
        print(f'Прочитано байт: {len(read_result)}')
        print(f'Ответ: {read_result}')
        current_battery_level = int(read_result[8])
        if current_battery_level == 0:
            current_battery_level = self.last_nonzero_level
        else:
            self.last_nonzero_level = current_battery_level
        print(f'Текущий заряд: {current_battery_level}%')
        return current_battery_level


class Pulsar:
    # Official Fusion uses SET_REPORT Output (wValue 0x0208) on interface 1,
    # not Feature reports — so hidapi write() is required, not send_feature_report().
    POWER_CMD = 0x04
    REPORT_ID = 0x08
    name = 'Pulsar'
    vid = 0x3554

    def __init__(self, vid):
        self.mouse = None

        devices = hid.enumerate(vid)
        if not devices:
            raise Exception('No Pulsar devices found.')

        # Prefer MI_01 (wIndex=1 in the USB capture); try others only as fallback.
        devices = sorted(
            devices,
            key=lambda d: 0 if d.get('interface_number') == 1 else 1,
        )

        for device in devices:
            try:
                mouse = hid.Device(path=device['path'])
                print(
                    f'Mouse found, interface_number={device.get("interface_number")}, '
                    f'usage_page=0x{device.get("usage_page", 0):04x}, path={device["path"]!r}'
                )
                try:
                    self.mouse = mouse
                    self.mouse.nonblocking = 1
                    self.get_battery()
                    break
                except TimeoutError:
                    raise
                except Exception as e:
                    print(e)
                    self.mouse = None
                    mouse.close()
                    continue
            except hid.HIDException as e:
                print(f'Cannot open with path: {e}')
                continue

        if self.mouse is None:
            raise Exception('No usable Pulsar HID interface found.')

    def checksum(self, *values):
        return ctypes.c_uint8(0x55 - sum(values)).value

    def get_battery(self):
        body = [self.REPORT_ID, self.POWER_CMD] + [0x00] * 14
        payload = bytes([*body, self.checksum(*body)])
        self.mouse.write(payload)
        time.sleep(0.05)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            read_result = self.mouse.read(17, timeout=500)
            if read_result and len(read_result) >= 7 and read_result[1] == self.POWER_CMD:
                print(f'Got battery: {int(read_result[6])}')
                return int(read_result[6])
        raise TimeoutError('Timed out waiting for Pulsar power response')


known_mouses = {WLMouse: 0x36A7, Pulsar: 0x3554}


def find_mouse():
    connected_vids = set()
    devices = hid.enumerate()
    for device in devices:
        connected_vids.add(device['vendor_id'])
    for vendor, vids in known_mouses.items():
        if vids in connected_vids:
            while True:
                try:
                    return vendor(vids)
                except TimeoutError:
                    time.sleep(10)
    raise Exception('No supported device found.')


def create_battery_icon(percent):
    width = 64
    height = 64
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    try:
        # custom font should be in the project folder
        font = ImageFont.truetype('arial.ttf', 66)
    except IOError:
        font = ImageFont.load_default()

    text = f'{percent}'
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    position = ((width - text_width) / 2, (height - text_height - 14) / 2)

    # low battery treshold color
    color = (192, 254, 4) if percent > 25 else (234, 11, 16)

    draw.text(position, text, fill=color, font=font)
    return image


def on_click(icon, item):
    if str(item) == 'Exit':
        icon.stop()
        sys.exit(0)  # exit


def update_icon(icon, mouse):
    current_battery_level = mouse.get_battery()
    print('Updating...')
    icon.icon = create_battery_icon(current_battery_level)
    icon.title = f'WLmouse Battery: {current_battery_level}%'
    # Планируем следующее обновление через 300 секунд (5 минут)
    icon.update_menu()  # Обновляем меню, если оно есть
    # Используем таймер для следующего вызова
    # icon.remaining_time = 300
    print(current_battery_level)


def main():
    mouse = find_mouse()
    current_battery_level = mouse.get_battery()

    image = create_battery_icon(current_battery_level)

    menu = pystray.Menu(pystray.MenuItem('Exit', on_click),
                        pystray.MenuItem('Update', lambda x: update_icon(x, mouse)))

    icon = pystray.Icon('wlmouse_battery', image, f'WLmouse Battery: {current_battery_level}%', menu)

    def updater(icon):
        while True:
            time.sleep(300)  # 5 минут
            # Обновляем иконку в главном потоке, так как работа с GUI потокобезопасна не всегда
            # Используем метод `update_menu`, чтобы вызвать код в главном потоке
            # или просто ставим новую иконку через `icon.icon = ...`
            battery_level = mouse.get_battery()
            icon.icon = create_battery_icon(battery_level)
            icon.title = f'{mouse.name} Battery: {battery_level}%'
            print(f'battery updated: {battery_level}%')

    thread = threading.Thread(target=updater, args=(icon,), daemon=True)
    thread.start()

    # Запускаем иконку (этот метод блокирует выполнение до выхода)
    icon.run()


if __name__ == '__main__':
    main()
