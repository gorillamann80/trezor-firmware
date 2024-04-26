import ustruct  # pyright: ignore[reportMissingModuleSource]
from typing import TYPE_CHECKING  # pyright:ignore[reportShadowedImports]

from storage.cache_thp import TAG_LENGTH, ChannelCache
from trezor import log, loop, protobuf, utils, workflow
from trezor.enums import FailureType
from trezor.wire.thp import interface_manager, received_message_handler

from . import (
    ChannelContext,
    ChannelState,
    checksum,
    control_byte,
    crypto,
    memory_manager,
)
from . import thp_session as THP
from .checksum import CHECKSUM_LENGTH
from .thp_messages import ENCRYPTED_TRANSPORT, ERROR, InitHeader
from .thp_session import ThpError
from .writer import (
    CONT_DATA_OFFSET,
    INIT_DATA_OFFSET,
    MESSAGE_TYPE_LENGTH,
    write_payload_to_wire,
)

if __debug__:
    from . import state_to_str

if TYPE_CHECKING:
    from trezorio import WireInterface  # pyright: ignore[reportMissingImports]


class Channel(ChannelContext):
    def __init__(self, channel_cache: ChannelCache) -> None:
        if __debug__:
            log.debug(__name__, "channel initialization")
        iface: WireInterface = interface_manager.decode_iface(channel_cache.iface)
        super().__init__(iface, channel_cache)
        self.channel_cache = channel_cache
        self.is_cont_packet_expected: bool = False
        self.expected_payload_length: int = 0
        self.bytes_read: int = 0

    # ACCESS TO CHANNEL_DATA

    def get_channel_state(self) -> int:
        state = int.from_bytes(self.channel_cache.state, "big")
        if __debug__:
            log.debug(__name__, "get_channel_state: %s", state_to_str(state))
        return state

    def set_channel_state(self, state: ChannelState) -> None:
        self.channel_cache.state = bytearray(state.to_bytes(1, "big"))
        if __debug__:
            log.debug(__name__, "set_channel_state: %s", state_to_str(state))

    def set_buffer(self, buffer: utils.BufferType) -> None:
        self.buffer = buffer
        if __debug__:
            log.debug(__name__, "set_buffer: %s", type(self.buffer))

    # CALLED BY THP_MAIN_LOOP

    async def receive_packet(self, packet: utils.BufferType):
        if __debug__:
            log.debug(__name__, "receive_packet")

        await self._handle_received_packet(packet)

        if __debug__:
            log.debug(__name__, "self.buffer: %s", utils.get_bytes_as_str(self.buffer))

        if self.expected_payload_length + INIT_DATA_OFFSET == self.bytes_read:
            self._finish_message()
            await received_message_handler.handle_received_message(self, self.buffer)
        elif self.expected_payload_length + INIT_DATA_OFFSET > self.bytes_read:
            self.is_cont_packet_expected = True
        else:
            raise ThpError(
                "Read more bytes than is the expected length of the message, this should not happen!"
            )

    async def _handle_received_packet(self, packet: utils.BufferType) -> None:
        ctrl_byte = packet[0]
        if control_byte.is_continuation(ctrl_byte):
            await self._handle_cont_packet(packet)
        else:
            await self._handle_init_packet(packet)

    async def _handle_init_packet(self, packet: utils.BufferType) -> None:
        if __debug__:
            log.debug(__name__, "handle_init_packet")
        ctrl_byte, _, payload_length = ustruct.unpack(">BHH", packet)
        self.expected_payload_length = payload_length
        packet_payload = packet[5:]
        # If the channel does not "own" the buffer lock, decrypt first packet
        # TODO do it only when needed!
        if control_byte.is_encrypted_transport(ctrl_byte):
            packet_payload = self._decrypt_single_packet_payload(packet_payload)

        self.buffer = memory_manager.select_buffer(
            self.get_channel_state(),
            self.buffer,
            packet_payload,
            payload_length,
        )
        await self._buffer_packet_data(self.buffer, packet, 0)

        if __debug__:
            log.debug(__name__, "handle_init_packet - payload len: %d", payload_length)
            log.debug(__name__, "handle_init_packet - buffer len: %d", len(self.buffer))

    async def _handle_cont_packet(self, packet: utils.BufferType) -> None:
        if __debug__:
            log.debug(__name__, "handle_cont_packet")
        if not self.is_cont_packet_expected:
            raise ThpError("Continuation packet is not expected, ignoring")
        await self._buffer_packet_data(self.buffer, packet, CONT_DATA_OFFSET)

    def _decrypt_single_packet_payload(self, payload: bytes) -> bytearray:
        payload_buffer = bytearray(payload)
        crypto.decrypt(b"\x00", b"\x00", payload_buffer, INIT_DATA_OFFSET, len(payload))
        return payload_buffer

    def decrypt_buffer(self, message_length: int) -> None:
        if not isinstance(self.buffer, bytearray):
            self.buffer = bytearray(self.buffer)
        crypto.decrypt(
            b"\x00",
            b"\x00",
            self.buffer,
            INIT_DATA_OFFSET,
            message_length - INIT_DATA_OFFSET - CHECKSUM_LENGTH,
        )

    def _encrypt(self, buffer: bytearray, noise_payload_len: int) -> None:
        if __debug__:
            log.debug(__name__, "encrypt")
        min_required_length = noise_payload_len + TAG_LENGTH + CHECKSUM_LENGTH
        if len(buffer) < min_required_length or not isinstance(buffer, bytearray):
            new_buffer = bytearray(min_required_length)
            utils.memcpy(new_buffer, 0, buffer, 0)
            buffer = new_buffer
        tag = crypto.encrypt(
            b"\x00",
            b"\x00",
            buffer,
            0,
            noise_payload_len,
        )
        buffer[noise_payload_len : noise_payload_len + TAG_LENGTH] = tag

    async def _buffer_packet_data(
        self, payload_buffer: utils.BufferType, packet: utils.BufferType, offset: int
    ):
        self.bytes_read += utils.memcpy(payload_buffer, self.bytes_read, packet, offset)

    def _finish_message(self):
        self.bytes_read = 0
        self.expected_payload_length = 0
        self.is_cont_packet_expected = False

    # CALLED BY WORKFLOW / SESSION CONTEXT

    async def write(self, msg: protobuf.MessageType, session_id: int = 0) -> None:
        if __debug__:
            log.debug(__name__, "write message: %s", msg.MESSAGE_NAME)
        noise_payload_len = memory_manager.encode_into_buffer(
            memoryview(self.buffer), msg, session_id
        )
        await self.write_and_encrypt(self.buffer[:noise_payload_len])

    async def write_error(self, err_type: FailureType, message: str) -> None:
        if __debug__:
            log.debug(__name__, "write_error")
        msg_size = memory_manager.encode_error_into_buffer(
            memoryview(self.buffer), err_type, message
        )
        data_length = MESSAGE_TYPE_LENGTH + msg_size
        header: InitHeader = InitHeader(
            ERROR, self.get_channel_id_int(), data_length + CHECKSUM_LENGTH
        )
        chksum = checksum.compute(
            header.to_bytes() + memoryview(self.buffer[:data_length])
        )

        utils.memcpy(self.buffer, data_length, chksum, 0)
        await write_payload_to_wire(
            self.iface, header, memoryview(self.buffer[: data_length + CHECKSUM_LENGTH])
        )

    async def write_and_encrypt(self, payload: bytes) -> None:
        payload_length = len(payload)

        if not isinstance(self.buffer, bytearray):
            self.buffer = bytearray(self.buffer)
        self._encrypt(self.buffer, payload_length)
        payload_length = payload_length + TAG_LENGTH

        if self.write_task_spawn is not None:
            self.write_task_spawn.close()  # UPS TODO migh break something
            print("\nCLOSED\n")
        self._prepare_write()
        self.write_task_spawn = loop.spawn(
            self._write_encrypted_payload_loop(
                ENCRYPTED_TRANSPORT, memoryview(self.buffer[:payload_length])
            )
        )

    async def write_handshake_message(self, ctrl_byte: int, payload: bytes) -> None:
        self._prepare_write()
        self.write_task_spawn = loop.spawn(
            self._write_encrypted_payload_loop(ctrl_byte, payload)
        )

    def _prepare_write(self) -> None:
        # TODO add condition that disallows to write when can_send_message is false
        THP.sync_set_can_send_message(self.channel_cache, False)

    async def _write_encrypted_payload_loop(
        self, ctrl_byte: int, payload: bytes
    ) -> None:
        if __debug__:
            log.debug(__name__, "write_encrypted_payload_loop")
        payload_len = len(payload) + CHECKSUM_LENGTH
        sync_bit = THP.sync_get_send_bit(self.channel_cache)
        ctrl_byte = control_byte.add_sync_bit_to_ctrl_byte(ctrl_byte, sync_bit)
        header = InitHeader(ctrl_byte, self.get_channel_id_int(), payload_len)
        chksum = checksum.compute(header.to_bytes() + payload)
        payload = payload + chksum

        while True:
            if __debug__:
                log.debug(
                    __name__,
                    "write_encrypted_payload_loop - loop start, sync_bit: %d, sync_send_bit: %d",
                    (header.ctrl_byte & 0x10) >> 4,
                    THP.sync_get_send_bit(self.channel_cache),
                )
            await write_payload_to_wire(self.iface, header, payload)
            self.waiting_for_ack_timeout = loop.spawn(self._wait_for_ack())
            try:
                if THP.sync_can_send_message(self.channel_cache):
                    # TODO This can happen when ack is received before the message was sent,
                    # but after it was scheduled to be sent (i.e. ACK was already expected)
                    # This case should be removed or improved upon before production.
                    break
                else:
                    await self.waiting_for_ack_timeout
            except loop.TaskClosed:
                break

        THP.sync_set_send_bit_to_opposite(self.channel_cache)

        # Let the main loop be restarted and clear loop, if there is no other
        # workflow and the state is ENCRYPTED_TRANSPORT
        if self._can_clear_loop():
            if __debug__:
                log.debug(__name__, "clearing loop from channel")
            loop.clear()

    def _can_clear_loop(self) -> bool:
        return (
            not workflow.tasks
        ) and self.get_channel_state() is ChannelState.ENCRYPTED_TRANSPORT

    async def _wait_for_ack(self) -> None:
        await loop.sleep(1000)