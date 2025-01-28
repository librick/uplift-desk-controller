from bleak import BleakClient, BleakGATTCharacteristic
from bleak.exc import BleakDBusError
from bleak.uuids import normalize_uuid_16
from typing import Self
import time

from utils import height_conv_to_in

desk_height_uuid = normalize_uuid_16(0xfe62)
desk_control_uuid = normalize_uuid_16(0xfe61)

wake_uuid = [0xf1, 0xf1, 0x00, 0x00, 0x00, 0x7e] # The content of this command actually doesn't seem to matter, the desk just needs to wake up
sit_preset_uuid = [0xf1, 0xf1, 0x05, 0x00, 0x05, 0x7e]
stand_preset_uuid = [0xf1, 0xf1, 0x06, 0x00, 0x06, 0x7e]
raise_button_uuid = [0xf1, 0xf1, 0x01, 0x00, 0x01, 0x7e]
lower_button_uuid = [0xf1, 0xf1, 0x02, 0x00, 0x02, 0x7e]
status_uuid = [0xf1, 0xf1, 0x07, 0x00, 0x07, 0x7e]

timeout = 8.0 # The desk times out it's "awake" state after 10 seconds of inactivity, but it takes this code about a 2 seconds to figure out that the desk is no longer awake

class Desk:
    def __init__(self, address, name, bleak_client: BleakClient = None) -> Self:
        self.address = address
        self.name = name
        self._height: float = 0.0
        self.bleak_client = bleak_client
        self._moving = False
        self._last_heights = []

    @property
    def height(self):
        return self._height

    @property
    def moving(self):
        return self._moving

    def _set_moving(self, value: bool):
        self._moving = value
        self._last_action_time = time.time()

    async def move_to_standing(self, bleak_client: BleakClient = None) -> None:
        client = bleak_client or self.bleak_client

        if (client is None):
            raise Exception("No bleak client provided")
        
        await self._awaken(client)
        await client.write_gatt_char(desk_control_uuid, stand_preset_uuid, False)

    async def move_to_sitting(self, bleak_client: BleakClient = None) -> None:
        client = bleak_client or self.bleak_client

        if (client is None):
            raise Exception("No bleak client provided")
        
        await self._awaken(client)
        await client.write_gatt_char(desk_control_uuid, sit_preset_uuid, False)

    async def press_raise(self, bleak_client: BleakClient = None) -> None:
        client = bleak_client or self.bleak_client

        if (client is None):
            raise Exception("No bleak client provided")
        
        await self._awaken(client)
        await client.write_gatt_char(desk_control_uuid, raise_button_uuid, False)

    async def press_lower(self, bleak_client: BleakClient = None) -> None:
        client = bleak_client or self.bleak_client

        if (client is None):
            raise Exception("No bleak client provided")
        
        await self._awaken(client)
        await client.write_gatt_char(desk_control_uuid, lower_button_uuid, False)

    async def start_notify(self, bleak_client: BleakClient = None) -> None:
        client = bleak_client or self.bleak_client

        if (client is None):
            raise Exception("No bleak client provided")
        
        await client.start_notify(desk_height_uuid, self._height_notify_callback)

    async def stop_notify(self, bleak_client: BleakClient = None) -> None:
        client = bleak_client or self.bleak_client

        if (client is None):
            raise Exception("No bleak client provided")
        
        try:
            await client.stop_notify(desk_height_uuid)
        except BleakDBusError:
            pass

    async def read_height(self, bleak_client: BleakClient = None) -> float:
        client = bleak_client or self.bleak_client

        if (client is None):
            raise Exception("No bleak client provided")
        
        self._last_action_time = time.time()
        await client.write_gatt_char(desk_control_uuid, status_uuid, False)
        self._height = height_conv_to_in(await client.read_gatt_char(desk_height_uuid))
        return self.height

    def __str__(self):
        return f"{self.name} - {self.address}"

    def _height_notify_callback(self, sender: BleakGATTCharacteristic, data: bytearray):
        print(f"Received height update: {height_conv_to_in(data)}; Moving: {self.moving}")
        self._height = height_conv_to_in(data)

        if (not self.moving
            and (len(self._last_heights) == 0 or self._last_heights[-1] != self._height)):
            self._set_moving(True)

        self._last_heights.append(self._height)
        if len(self._last_heights) > 4:
            if (self.moving
                and self._last_action_time + 1 < time.time() # Only set moving to false if we've been moving for more than 1 second (sometimes the first few height updates are the same)
                and self._last_heights[0] == self._height 
                and self._last_heights[1] == self._height
                and self._last_heights[2] == self._height
                and self._last_heights[3] == self._height):
                self._set_moving(False)

            self._last_heights.pop(0)

    async def _awaken(self, bleak_client: BleakClient = None) -> None:
        client = bleak_client or self.bleak_client

        if (client is None):
            raise Exception("No bleak client provided")

        await bleak_client.write_gatt_char(desk_control_uuid, wake_uuid, False)