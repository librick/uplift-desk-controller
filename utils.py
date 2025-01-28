def height_conv_to_in(height_bytes: bytearray) -> float:
    return int.from_bytes(height_bytes[-5:-3], "big") / 10.0