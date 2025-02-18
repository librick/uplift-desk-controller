import asyncio
import time
import sys
from bleak import BleakScanner, BleakClient
from bleak.uuids import normalize_uuid_16
from bleak.backends.device import BLEDevice

from uplift import Desk, discover

primary_service_uuid_for_discovery  = normalize_uuid_16(0xfe60)

timeout = 10.0

def print_command_options():

    print("Commands:")
    print("    h - print this help message")
    print("    u - move_to_standing")
    print("    d - move_to_sitting")
    print("    r - press_raise")
    print("    l - press_lower")
    print("    e - exit")

async def main():
    desks: list[BLEDevice] = await discover()
    if len(desks) == 0:
        print("No desks found")
        return
    print(f"Found {len(desks)} desk(s)")
    for desk in desks:
        print(f"    - {desk.name} - {desk.address}")       

    first_desk = desks[0]
    print(f"Connecting to {first_desk.name} - {first_desk.address}...")

    async with BleakClient(first_desk) as bleak_client:
        print(f"Connected to {bleak_client.address}")
        
        desk = Desk(first_desk.address, first_desk.name, bleak_client)

        await desk.start_notify()
        await desk.read_height(bleak_client)
        print(f"Height: {desk.height} in")
        
        print("Start typing and press ENTER...\n Press h for help")

        loop = asyncio.get_running_loop()

        while True:
            data = await loop.run_in_executor(None, sys.stdin.buffer.readline)

            # data will be empty on EOF (e.g. CTRL+D on *nix)
            if not data:
                break

            if (data == b"u\n"):
                print("move_to_standing")
                await desk.move_to_standing()
            elif (data == b"d\n"):
                print("move_to_sitting")
                await desk.move_to_sitting()
            elif (data == b"r\n"):
                print("press_raise")
                await desk.press_raise()
            elif (data == b"l\n"):
                print("press_lower")
                await desk.press_lower()
            elif (data == b"h\n"):
                print_command_options()
            elif (data == b"e\n"):
                print("exit")
                break

        await desk.stop_notify()
        print(f"Height: {desk.height} in")

if __name__ == "__main__":
    asyncio.run(main())