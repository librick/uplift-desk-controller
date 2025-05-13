"""Top level package for uplift-desk"""

from __future__ import annotations

__author__ = """Bennett Wendorf"""
__email__ = """bennett@bennettwendorf.dev"""

from bleak import BleakScanner, BleakClient, BleakGATTCharacteristic
from bleak.exc import BleakDBusError
from bleak.uuids import normalize_uuid_16
from bleak.backends.device import BLEDevice
from typing import Self
import time

from .utils import height_conv_to_in

# --- Service UUIDs ---
# The block FE60 is allocated to Lierda Science & Technology Group Co., Ltd.
_service_vendor_discovery = normalize_uuid_16(0xFE60)

# --- Characteristic UUIDs ---
# Generic Access characteristic that stores the device name.
_char_std_device_name = normalize_uuid_16(0x2A00)
# Write+Notify. The desk firmware uses this internally to derive its device name.
_char_vendor_desk_name = normalize_uuid_16(0xFE63)
# Read+Notify. The desk pushes its current height measurements over this characteristic,
_char_vendor_desk_height = normalize_uuid_16(0xFE62)
# Write. All desk commands (wake, sit-preset, stand-preset, raise, lower, request status) are sent as 6-byte payloads.
_char_vendor_desk_control = normalize_uuid_16(0xFE61)

# --- Command Payloads ---
_cmd_wake = [
    0xF1,
    0xF1,
    0x00,
    0x00,
    0x00,
    0x7E,
]  # The content of this command actually doesn't seem to matter, the desk just needs to wake up
_cmd_vendor_preset_sit = [0xF1, 0xF1, 0x05, 0x00, 0x05, 0x7E]
_cmd_vendor_preset_stand = [0xF1, 0xF1, 0x06, 0x00, 0x06, 0x7E]
_cmd_vendor_button_raise = [0xF1, 0xF1, 0x01, 0x00, 0x01, 0x7E]
_cmd_vendor_button_lower = [0xF1, 0xF1, 0x02, 0x00, 0x02, 0x7E]
_cmd_vendor_status = [0xF1, 0xF1, 0x07, 0x00, 0x07, 0x7E]

_scanner_timeout = 10.0


def discover(scanner: BleakScanner = None) -> list[BLEDevice]:
    if scanner is None:
        scanner = BleakScanner()

    return scanner.discover(
        timeout=_scanner_timeout, service_uuids=[_service_vendor_discovery]
    )


class Desk:
    def __init__(
        self, address: str, name: str, bleak_client: BleakClient = None
    ) -> Self:
        self.address = address
        self.name = name
        self._height: float = 0.0
        self.bleak_client = bleak_client
        self._moving = False
        self._last_heights = []
        self._notification_callbacks_desk_name: list[callable] = []
        self._notification_callbacks_height: list[callable] = []

    @property
    def height(self):
        return self._height

    @property
    def moving(self):
        return self._moving

    def _get_client(self, bleak_client: BleakClient) -> BleakClient:
        client = bleak_client or self.bleak_client

        if client is None:
            raise RuntimeError("No bleak client provided")
        return client

    def _set_moving(self, value: bool):
        self._moving = value
        self._last_action_time = time.time()

    async def move_to_standing(self, bleak_client: BleakClient = None) -> None:
        client = self._get_client(bleak_client)
        await self._awaken(client)
        await client.write_gatt_char(
            _char_vendor_desk_control, _cmd_vendor_preset_stand, False
        )

    async def move_to_sitting(self, bleak_client: BleakClient = None) -> None:
        client = self._get_client(bleak_client)
        await self._awaken(client)
        await client.write_gatt_char(
            _char_vendor_desk_control, _cmd_vendor_preset_sit, False
        )

    async def press_raise(self, bleak_client: BleakClient = None) -> None:
        client = self._get_client(bleak_client)
        await self._awaken(client)
        await client.write_gatt_char(
            _char_vendor_desk_control, _cmd_vendor_button_raise, False
        )

    async def press_lower(self, bleak_client: BleakClient = None) -> None:
        client = self._get_client(bleak_client)
        await self._awaken(client)
        await client.write_gatt_char(
            _char_vendor_desk_control, _cmd_vendor_button_lower, False
        )

    async def start_notify(self, bleak_client: BleakClient = None) -> None:
        client = bleak_client or self.bleak_client

        await client.start_notify(
            _char_vendor_desk_name, self._notify_callback_desk_name
        )
        await client.start_notify(
            _char_vendor_desk_height, self._notify_callback_height
        )

    async def stop_notify(self, bleak_client: BleakClient = None) -> None:
        client = bleak_client or self.bleak_client

        if client is None:
            raise Exception("No bleak client provided")

        try:
            await client.stop_notify(_char_vendor_desk_height)
        except BleakDBusError:
            pass

    async def read_device_name(self, bleak_client: BleakClient = None):
        client = self._get_client(bleak_client)

        data = await client.read_gatt_char(_char_std_device_name)
        name = data.decode("utf-8", errors="ignore")
        print("Device name is:", name)
        return name

    async def write_desk_name(
        self, bleak_client: BleakClient = None, desk_name=None
    ) -> float:
        client = self._get_client(bleak_client)

        if desk_name is None:
            raise Exception("No desk_name provided")

        name_bytes = desk_name.encode("utf-8")
        header = bytes([0x01, 0xFC, 0x07, len(name_bytes)])
        packet = header + name_bytes

        print(f"Setting desk name: {desk_name}")
        self._last_action_time = time.time()
        await client.write_gatt_char(_char_vendor_desk_name, packet, False)

    async def read_height(self, bleak_client: BleakClient = None) -> float:
        client = self._get_client(bleak_client)

        self._last_action_time = time.time()
        await client.write_gatt_char(
            _char_vendor_desk_control, _cmd_vendor_status, False
        )
        self._height = height_conv_to_in(
            await client.read_gatt_char(_char_vendor_desk_height)
        )
        return self.height

    def register_callback_desk_name(self, callback: callable) -> None:
        self._notification_callbacks_desk_name.append(callback)

    def deregister_callback_desk_name(self, callback: callable) -> None:
        self._notification_callbacks_desk_name.remove(callback)

    def register_callback_height(self, callback: callable) -> None:
        self._notification_callbacks_height.append(callback)

    def deregister_callback_height(self, callback: callable) -> None:
        self._notification_callbacks_height.remove(callback)

    def __str__(self):
        return f"{self.name} - {self.address}"

    async def _notify_callback_desk_name(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ):
        # Anecdotally, the returned data is an ACK with a structure like:
        # - 0x04 - A length field indicating 4 bytes follow
        # - 0xFC, 0x07 - The write command opcode; the same as was sent in the write command header
        # - 0x01 - A "success" status code
        # - 0x00 - A checksum or zero-padding
        for callback in self._notification_callbacks_desk_name:
            await callback(self)

    async def _notify_callback_height(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ):
        self._height = height_conv_to_in(data)

        if len(self._last_heights) > 0 and self._last_heights[-1] != self._height:
            self._set_moving(True)

        self._last_heights.append(self._height)
        if len(self._last_heights) > 4:
            if (
                self.moving
                and self._last_action_time + 1
                < time.time()  # Only set moving to false if we've been moving for more than 1 second (sometimes the first few height updates are the same)
                and self._last_heights[0] == self._height
                and self._last_heights[1] == self._height
                and self._last_heights[2] == self._height
                and self._last_heights[3] == self._height
            ):
                self._set_moving(False)

            self._last_heights.pop(0)

        for callback in self._notification_callbacks_height:
            await callback(self)

    async def _awaken(self, bleak_client: BleakClient = None) -> None:
        client = bleak_client or self.bleak_client

        if client is None:
            raise Exception("No bleak client provided")

        await bleak_client.write_gatt_char(_char_vendor_desk_control, _cmd_wake, False)
