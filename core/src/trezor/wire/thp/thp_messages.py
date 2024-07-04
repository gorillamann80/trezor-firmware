import ustruct
from micropython import const

from storage.cache_thp import BROADCAST_CHANNEL_ID
from trezor import protobuf, utils
from trezor.enums import ThpPairingMethod
from trezor.messages import ThpDeviceProperties

from .. import message_handler

CODEC_V1 = const(0x3F)
CONTINUATION_PACKET = const(0x80)
HANDSHAKE_INIT_REQ = const(0x00)
HANDSHAKE_INIT_RES = const(0x01)
HANDSHAKE_COMP_REQ = const(0x02)
HANDSHAKE_COMP_RES = const(0x03)
ENCRYPTED_TRANSPORT = const(0x04)

CONTINUATION_PACKET_MASK = const(0x80)
ACK_MASK = const(0xF7)
DATA_MASK = const(0xE7)

ACK_MESSAGE = const(0x20)
ERROR = const(0x42)
CHANNEL_ALLOCATION_REQ = const(0x40)
_CHANNEL_ALLOCATION_RES = const(0x41)

TREZOR_STATE_UNPAIRED = b"\x00"
TREZOR_STATE_PAIRED = b"\x01"

if __debug__:
    from trezor import log


class PacketHeader:
    format_str_init = ">BHH"
    format_str_cont = ">BH"

    def __init__(self, ctrl_byte: int, cid: int, length: int) -> None:
        self.ctrl_byte = ctrl_byte
        self.cid = cid
        self.length = length

    def to_bytes(self) -> bytes:
        return ustruct.pack(self.format_str_init, self.ctrl_byte, self.cid, self.length)

    def pack_to_init_buffer(self, buffer, buffer_offset=0) -> None:
        ustruct.pack_into(
            self.format_str_init,
            buffer,
            buffer_offset,
            self.ctrl_byte,
            self.cid,
            self.length,
        )

    def pack_to_cont_buffer(self, buffer, buffer_offset=0) -> None:
        ustruct.pack_into(
            self.format_str_cont, buffer, buffer_offset, CONTINUATION_PACKET, self.cid
        )

    @classmethod
    def get_error_header(cls, cid, length):
        return cls(ERROR, cid, length)

    @classmethod
    def get_channel_allocation_response_header(cls, length):
        return cls(_CHANNEL_ALLOCATION_RES, BROADCAST_CHANNEL_ID, length)


_ENCODED_DEVICE_PROPERTIES: bytes | None = None

_ERROR_UNALLOCATED_CHANNEL = (
    b"\x55\x4e\x41\x4c\x4c\x4f\x43\x41\x54\x45\x44\x5f\x53\x45\x53\x53\x49\x4f\x4e"
)
_ENABLED_PAIRING_METHODS = [
    ThpPairingMethod.CodeEntry,
    ThpPairingMethod.QrCode,
    ThpPairingMethod.NFC_Unidirectional,
]


def _get_device_properties() -> ThpDeviceProperties:
    # TODO define model variants
    return ThpDeviceProperties(
        pairing_methods=_ENABLED_PAIRING_METHODS,
        internal_model=utils.INTERNAL_MODEL,
        model_variant=0,
        bootloader_mode=False,
        protocol_version=3,
    )


def get_encoded_device_properties() -> bytes:
    global _ENCODED_DEVICE_PROPERTIES
    if _ENCODED_DEVICE_PROPERTIES is None:
        props = _get_device_properties()
        length = protobuf.encoded_length(props)
        _ENCODED_DEVICE_PROPERTIES = bytearray(length)
        protobuf.encode(_ENCODED_DEVICE_PROPERTIES, props)
    return _ENCODED_DEVICE_PROPERTIES


def get_channel_allocation_response(nonce: bytes, new_cid: bytes) -> bytes:
    props_msg = get_encoded_device_properties()
    return nonce + new_cid + props_msg


def get_error_unallocated_channel() -> bytes:
    return _ERROR_UNALLOCATED_CHANNEL


def get_handshake_completion_response(paired: bool) -> bytes:
    if paired:
        return (
            TREZOR_STATE_PAIRED
            + b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x10\x11\x12\x13\x14\x15"
        )
    return (
        TREZOR_STATE_UNPAIRED
        + b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x10\x11\x12\x13\x14\x15"
    )


def decode_message(
    buffer: bytes, msg_type: int, message_name: str | None = None
) -> protobuf.MessageType:
    if __debug__:
        log.debug(__name__, "decode message")
    if message_name is not None:
        expected_type = protobuf.type_for_name(message_name)
    else:
        expected_type = protobuf.type_for_wire(msg_type)
    x = message_handler.wrap_protobuf_load(buffer, expected_type)
    return x
