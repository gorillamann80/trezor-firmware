from micropython import const
from trezorcrypto import crc
from typing import TYPE_CHECKING

from trezor import io, log, loop, utils
from trezor.wire.thp.thp_messages import PacketHeader

INIT_DATA_OFFSET = const(5)
CONT_DATA_OFFSET = const(3)
PACKET_LENGTH = const(64)
CHECKSUM_LENGTH = const(4)
MAX_PAYLOAD_LEN = const(60000)
MESSAGE_TYPE_LENGTH = const(2)

if TYPE_CHECKING:
    from trezorio import WireInterface
    from typing import Sequence


async def write_payload_to_wire_and_add_checksum(
    iface: WireInterface, header: PacketHeader, transport_payload: bytes
):
    header_checksum: int = crc.crc32(header.to_bytes())
    checksum: bytes = crc.crc32(transport_payload, header_checksum).to_bytes(
        CHECKSUM_LENGTH, "big"
    )
    data = (transport_payload, checksum)
    await write_payloads_to_wire(iface, header, data)


async def write_payloads_to_wire(
    iface: WireInterface, header: PacketHeader, data: Sequence[bytes]
):
    n_of_data = len(data)
    total_length = sum(len(item) for item in data)

    current_data_idx = 0
    current_data_offset = 0

    packet = bytearray(PACKET_LENGTH)
    header.pack_to_init_buffer(packet)
    packet_offset: int = INIT_DATA_OFFSET
    packet_number = 0
    nwritten = 0
    while nwritten < total_length:
        if packet_number == 1:
            header.pack_to_cont_buffer(packet)
        if packet_number >= 1 and nwritten >= total_length - PACKET_LENGTH:
            packet[:] = bytearray(PACKET_LENGTH)
            header.pack_to_cont_buffer(packet)
        while True:
            n = utils.memcpy(
                packet, packet_offset, data[current_data_idx], current_data_offset
            )
            packet_offset += n
            current_data_offset += n
            nwritten += n

            if packet_offset < PACKET_LENGTH:
                current_data_idx += 1
                current_data_offset = 0
                if current_data_idx >= n_of_data:
                    break
            elif packet_offset == PACKET_LENGTH:
                break
            else:
                raise Exception("Should not happen!!!")
        packet_number += 1
        packet_offset = CONT_DATA_OFFSET
        await _write_packet_to_wire(iface, packet)


async def _write_packet_to_wire(iface: WireInterface, packet: utils.BufferType) -> None:
    while True:
        await loop.wait(iface.iface_num() | io.POLL_WRITE)
        if __debug__:
            log.debug(
                __name__, "write_packet_to_wire: %s", utils.get_bytes_as_str(packet)
            )
        n = iface.write(packet)
        if n == len(packet):
            return
