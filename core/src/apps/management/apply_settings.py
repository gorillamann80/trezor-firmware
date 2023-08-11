from typing import TYPE_CHECKING

import storage.device as storage_device
import trezortranslate as TR
import trezorui2
from trezor import utils
from trezor.enums import ButtonRequestType
from trezor.ui.layouts import confirm_action
from trezor.wire import DataError

if TYPE_CHECKING:
    from trezor.enums import SafetyCheckLevel
    from trezor.messages import ApplySettings, Success


BRT_PROTECT_CALL = ButtonRequestType.ProtectCall  # CACHE

if utils.INTERNAL_MODEL in ("T1B1", "T2B1"):

    def _validate_homescreen_model_specific(homescreen: bytes) -> None:
        from trezor.ui import HEIGHT, WIDTH

        try:
            w, h, is_grayscale = trezorui2.toif_info(homescreen)
        except ValueError:
            raise DataError("Invalid homescreen")
        if w != WIDTH or h != HEIGHT:
            raise DataError(f"Homescreen must be {WIDTH}x{HEIGHT} pixel large")
        if not is_grayscale:
            raise DataError("Homescreen must be grayscale")

else:

    def _validate_homescreen_model_specific(homescreen: bytes) -> None:
        from trezor.ui import HEIGHT, WIDTH

        try:
            w, h, mcu_height = trezorui2.jpeg_info(homescreen)
        except ValueError:
            raise DataError("Invalid homescreen")
        if w != WIDTH or h != HEIGHT:
            raise DataError(f"Homescreen must be {WIDTH}x{HEIGHT} pixel large")
        if mcu_height > 16:
            raise DataError("Unsupported jpeg type")
        try:
            trezorui2.jpeg_test(homescreen)
        except ValueError:
            raise DataError("Invalid homescreen")


def _validate_homescreen(homescreen: bytes) -> None:
    import storage.device as storage_device

    if homescreen == b"":
        return

    if len(homescreen) > storage_device.HOMESCREEN_MAXSIZE:
        raise DataError(
            f"Homescreen is too large, maximum size is {storage_device.HOMESCREEN_MAXSIZE} bytes"
        )

    _validate_homescreen_model_specific(homescreen)


async def apply_settings(msg: ApplySettings) -> Success:
    from trezor.messages import Success
    from trezor.wire import NotInitialized, ProcessError

    from apps.base import reload_settings_from_storage
    from apps.common import safety_checks

    if not storage_device.is_initialized():
        raise NotInitialized("Device is not initialized")

    homescreen = msg.homescreen  # local_cache_attribute
    label = msg.label  # local_cache_attribute
    auto_lock_delay_ms = msg.auto_lock_delay_ms  # local_cache_attribute
    use_passphrase = msg.use_passphrase  # local_cache_attribute
    passphrase_always_on_device = (
        msg.passphrase_always_on_device
    )  # local_cache_attribute
    display_rotation = msg.display_rotation  # local_cache_attribute
    msg_safety_checks = msg.safety_checks  # local_cache_attribute
    experimental_features = msg.experimental_features  # local_cache_attribute
    hide_passphrase_from_host = msg.hide_passphrase_from_host  # local_cache_attribute

    if (
        homescreen is None
        and label is None
        and use_passphrase is None
        and passphrase_always_on_device is None
        and display_rotation is None
        and auto_lock_delay_ms is None
        and msg_safety_checks is None
        and experimental_features is None
        and hide_passphrase_from_host is None
    ):
        raise ProcessError("No setting provided")

    if homescreen is not None:
        _validate_homescreen(homescreen)
        await _require_confirm_change_homescreen(homescreen)
        try:
            storage_device.set_homescreen(homescreen)
        except ValueError:
            raise DataError("Invalid homescreen")

    if label is not None:
        if len(label) > storage_device.LABEL_MAXLENGTH:
            raise DataError("Label too long")
        await _require_confirm_change_label(label)
        storage_device.set_label(label)

    if use_passphrase is not None:
        await _require_confirm_change_passphrase(use_passphrase)
        storage_device.set_passphrase_enabled(use_passphrase)

    if passphrase_always_on_device is not None:
        if not storage_device.is_passphrase_enabled():
            raise DataError("Passphrase is not enabled")
        await _require_confirm_change_passphrase_source(passphrase_always_on_device)
        storage_device.set_passphrase_always_on_device(passphrase_always_on_device)

    if auto_lock_delay_ms is not None:
        if auto_lock_delay_ms < storage_device.AUTOLOCK_DELAY_MINIMUM:
            raise ProcessError("Auto-lock delay too short")
        if auto_lock_delay_ms > storage_device.AUTOLOCK_DELAY_MAXIMUM:
            raise ProcessError("Auto-lock delay too long")
        await _require_confirm_change_autolock_delay(auto_lock_delay_ms)
        storage_device.set_autolock_delay_ms(auto_lock_delay_ms)

    if msg_safety_checks is not None:
        await _require_confirm_safety_checks(msg_safety_checks)
        safety_checks.apply_setting(msg_safety_checks)

    if display_rotation is not None:
        await _require_confirm_change_display_rotation(display_rotation)
        storage_device.set_rotation(display_rotation)

    if experimental_features is not None:
        await _require_confirm_experimental_features(experimental_features)
        storage_device.set_experimental_features(experimental_features)

    if hide_passphrase_from_host is not None:
        if safety_checks.is_strict():
            raise ProcessError("Safety checks are strict")
        await _require_confirm_hide_passphrase_from_host(hide_passphrase_from_host)
        storage_device.set_hide_passphrase_from_host(hide_passphrase_from_host)

    reload_settings_from_storage()

    return Success(message="Settings applied")


async def _require_confirm_change_homescreen(homescreen: bytes) -> None:
    from trezor.ui.layouts import confirm_homescreen

    await confirm_homescreen(homescreen)


async def _require_confirm_change_label(label: str) -> None:
    from trezor.ui.layouts import confirm_single

    await confirm_single(
        "set_label",
        TR.tr("device_name__title"),
        description=TR.tr("device_name__change_template"),
        description_param=label,
        verb=TR.tr("buttons__change"),
    )


async def _require_confirm_change_passphrase(use: bool) -> None:
    description = TR.tr("passphrase__turn_on") if use else TR.tr("passphrase__turn_off")
    verb = TR.tr("buttons__turn_on") if use else TR.tr("buttons__turn_off")
    await confirm_action(
        "set_passphrase",
        TR.tr("passphrase__title_settings"),
        description=description,
        verb=verb,
        br_code=BRT_PROTECT_CALL,
    )


async def _require_confirm_change_passphrase_source(
    passphrase_always_on_device: bool,
) -> None:
    description = (
        TR.tr("passphrase__always_on_device")
        if passphrase_always_on_device
        else TR.tr("passphrase__revoke_on_device")
    )
    await confirm_action(
        "set_passphrase_source",
        TR.tr("passphrase__title_source"),
        description=description,
        br_code=BRT_PROTECT_CALL,
    )


async def _require_confirm_change_display_rotation(rotation: int) -> None:
    if rotation == 0:
        label = TR.tr("rotation__north")
    elif rotation == 90:
        label = TR.tr("rotation__east")
    elif rotation == 180:
        label = TR.tr("rotation__south")
    elif rotation == 270:
        label = TR.tr("rotation__west")
    else:
        raise DataError("Unsupported display rotation")

    await confirm_action(
        "set_rotation",
        TR.tr("rotation__title_change"),
        description=TR.tr("rotation__change_template"),
        description_param=label,
        br_code=BRT_PROTECT_CALL,
    )


async def _require_confirm_change_autolock_delay(delay_ms: int) -> None:
    from trezor.strings import format_duration_ms

    await confirm_action(
        "set_autolock_delay",
        TR.tr("auto_lock__title"),
        description=TR.tr("auto_lock__change_template"),
        description_param=format_duration_ms(delay_ms),
        br_code=BRT_PROTECT_CALL,
    )


async def _require_confirm_safety_checks(level: SafetyCheckLevel) -> None:
    from trezor.enums import SafetyCheckLevel

    if level == SafetyCheckLevel.Strict:
        await confirm_action(
            "set_safety_checks",
            TR.tr("safety_checks__title"),
            description=TR.tr("safety_checks__enforce_strict"),
            br_code=BRT_PROTECT_CALL,
        )
    elif level in (SafetyCheckLevel.PromptAlways, SafetyCheckLevel.PromptTemporarily):
        description = (
            TR.tr("safety_checks__approve_unsafe_temporary")
            if level == SafetyCheckLevel.PromptTemporarily
            else TR.tr("safety_checks__approve_unsafe_always")
        )
        await confirm_action(
            "set_safety_checks",
            TR.tr("safety_checks__title_safety_override"),
            TR.tr("words__are_you_sure"),
            description,
            hold=True,
            verb=TR.tr("buttons__hold_to_confirm"),
            reverse=True,
            br_code=BRT_PROTECT_CALL,
        )
    else:
        raise ValueError  # enum value out of range


async def _require_confirm_experimental_features(enable: bool) -> None:
    if enable:
        await confirm_action(
            "set_experimental_features",
            TR.tr("experimental_mode__title"),
            TR.tr("experimental_mode__only_for_dev"),
            TR.tr("experimental_mode__enable"),
            reverse=True,
            br_code=BRT_PROTECT_CALL,
        )


async def _require_confirm_hide_passphrase_from_host(enable: bool) -> None:
    if enable:
        await confirm_action(
            "set_hide_passphrase_from_host",
            TR.tr("passphrase__title_hide"),
            description=TR.tr("passphrase__hide"),
            br_code=BRT_PROTECT_CALL,
        )
