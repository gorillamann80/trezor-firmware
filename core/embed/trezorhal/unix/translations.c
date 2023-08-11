#include "translations.h"
#include <string.h>
#include "common.h"
#include "flash.h"
#include "model.h"

void translations_write(uint8_t* data, uint32_t offset, uint32_t len) {
  ensure(flash_unlock_write(), "translations_write unlock");
  for (int i = 0; i < len; i++) {
    ensure(flash_area_write_byte(&TRANSLATIONS_AREA, offset + i, data[i]),
           "translations_write write");
  }
  ensure(flash_lock_write(), "translations_write lock");
}

const uint8_t* translations_read(uint32_t offset, uint32_t len) {
  return flash_area_get_address(&TRANSLATIONS_AREA, offset, len);
}

void translations_erase(void) {
  ensure(flash_area_erase(&TRANSLATIONS_AREA, NULL), "translations erase");
}
