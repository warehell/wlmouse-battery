import ctypes
import os
import sys

os.add_dll_directory(os.path.dirname(os.path.realpath(__file__)))
import hid
import pystray
import time
from PIL import Image, ImageDraw, ImageFont
import threading


class WLMouse:
    def __init__(self, vid):
        self.vid = 0x36A7
        self.last_nonzero_level = 1
        self.name = "WLmouse"

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
                    mouse.close()
                    continue

            except Exception as e:
                print(f"Cannot open with path: {e}")
                raise e

    def get_battery(self):
        command_buffer = [0x00] * 65  # got this command buffer from https://gm.wlmouse.gg/#/project/items
        command_buffer[3] = 0x2  # searched by 'getReport', 'getBat' in devtools (js)
        command_buffer[4] = 0x2  # this exact command buffer needed to get battery life response
        command_buffer[6] = 0x83
        write_result = self.mouse.send_feature_report(bytes(command_buffer))
        print(f"Отправлено байт: {write_result}")
        time.sleep(0.1)
        read_result = self.mouse.get_feature_report(0x0, 65)
        print(f"Прочитано байт: {len(read_result)}")
        print(f"Ответ: {read_result}")
        current_battery_level = int(read_result[8])
        if current_battery_level == 0:
            current_battery_level = self.last_nonzero_level
        else:
            self.last_nonzero_level = current_battery_level
        print(f"Текущий заряд: {current_battery_level}%")
        return current_battery_level


class Pulsar:
    def __init__(self, vid):
        self.name = "Pulsar"
        self.vid = 0x3554

        devices = hid.enumerate(vid)
        if not devices:
            raise Exception('No Pulsar devices found.')
        for device in devices:
            try:
                mouse = hid.Device(path=device['path'])
                print(f'Mouse found, interface_number:{device["path"]}')
                try:
                    self.mouse = mouse
                    self.get_battery()
                    break
                except Exception as e:
                    print(e)
                    mouse.close()
                    continue

            except Exception as e:
                print(f"Cannot open with path: {e}")
                raise e

    def checksum(self, *values):
        return ctypes.c_uint8(0x55 - sum(values)).value

    def get_battery(self):
        payload = bytes([
            0x08, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x49,  # checksum
        ])
        #self.mouse.write(payload)
        self.mouse.send_feature_report(payload)
        time.sleep(0.05)  # small delay may help
        while True:
            read_result = self.mouse.read(17, timeout=1000)
            if read_result and read_result[1] == 0x03:
                return int(read_result[6])


known_mouses = {
    WLMouse: 0x36A7,
    Pulsar: 0x3554,
}


def find_mouse():
    connected_vids = set()
    devices = hid.enumerate()
    for device in devices:
        connected_vids.add(device['vendor_id'])
    for vendor, vids in known_mouses.items():
        if vids in connected_vids:
            return vendor(vids)


def create_battery_icon(percent):
    width = 64
    height = 64
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    try:
        # custom font should be in the project folder
        font = ImageFont.truetype("arial.ttf", 66)
    except IOError:
        font = ImageFont.load_default()

    text = f"{percent}"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    position = ((width - text_width) / 2, (height - text_height - 14) / 2)

    # low battery treshold color
    color = (192, 254, 4) if percent > 25 else (234, 11, 16)

    draw.text(position, text, fill=color, font=font)
    return image


def on_click(icon, item):
    if str(item) == "Exit":
        icon.stop()
        sys.exit(0)  # exit


def update_icon(icon, mouse):
    current_battery_level = mouse.get_battery()
    print("Updating...")
    icon.icon = create_battery_icon(current_battery_level)
    icon.title = f"WLmouse Battery: {current_battery_level}%"
    # Планируем следующее обновление через 300 секунд (5 минут)
    icon.update_menu()  # Обновляем меню, если оно есть
    # Используем таймер для следующего вызова
    # icon.remaining_time = 300
    print(current_battery_level)


def main():
    mouse = find_mouse()
    current_battery_level = mouse.get_battery()

    image = create_battery_icon(current_battery_level)

    menu = pystray.Menu(
        pystray.MenuItem("Exit", on_click),
        pystray.MenuItem("Update", lambda x: update_icon(x, mouse)),
    )

    icon = pystray.Icon(
        "wlmouse_battery",
        image,
        f"WLmouse Battery: {current_battery_level}%",
        menu
    )

    def updater(icon):
        while True:
            time.sleep(300)  # 5 минут
            # Обновляем иконку в главном потоке, так как работа с GUI потокобезопасна не всегда
            # Используем метод `update_menu`, чтобы вызвать код в главном потоке
            # или просто ставим новую иконку через `icon.icon = ...`
            battery_level = mouse.get_battery()
            icon.icon = create_battery_icon(battery_level)
            icon.title = f"{mouse.name} Battery: {battery_level}%"
            print(f"battery updated: {battery_level}%")

    thread = threading.Thread(target=updater, args=(icon,), daemon=True)
    thread.start()

    # Запускаем иконку (этот метод блокирует выполнение до выхода)
    icon.run()


if __name__ == '__main__':
    main()