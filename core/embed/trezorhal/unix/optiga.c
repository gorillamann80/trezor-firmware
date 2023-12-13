/*
 * This file is part of the Trezor project, https://trezor.io/
 *
 * Copyright (c) SatoshiLabs
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#include "optiga.h"
#include <string.h>
#include "ecdsa.h"
#include "nist256p1.h"
#include "optiga_common.h"
#include "rand.h"

static const uint8_t DEVICE_CERT_CHAIN[] = {
    0x30, 0x82, 0x01, 0x9f, 0x30, 0x82, 0x01, 0x45, 0xa0, 0x03, 0x02, 0x01,
    0x02, 0x02, 0x04, 0x4e, 0xe2, 0xa5, 0x0f, 0x30, 0x0a, 0x06, 0x08, 0x2a,
    0x86, 0x48, 0xce, 0x3d, 0x04, 0x03, 0x02, 0x30, 0x4f, 0x31, 0x0b, 0x30,
    0x09, 0x06, 0x03, 0x55, 0x04, 0x06, 0x13, 0x02, 0x43, 0x5a, 0x31, 0x1e,
    0x30, 0x1c, 0x06, 0x03, 0x55, 0x04, 0x0a, 0x0c, 0x15, 0x54, 0x72, 0x65,
    0x7a, 0x6f, 0x72, 0x20, 0x43, 0x6f, 0x6d, 0x70, 0x61, 0x6e, 0x79, 0x20,
    0x73, 0x2e, 0x72, 0x2e, 0x6f, 0x2e, 0x31, 0x20, 0x30, 0x1e, 0x06, 0x03,
    0x55, 0x04, 0x03, 0x0c, 0x17, 0x54, 0x72, 0x65, 0x7a, 0x6f, 0x72, 0x20,
    0x4d, 0x61, 0x6e, 0x75, 0x66, 0x61, 0x63, 0x74, 0x75, 0x72, 0x69, 0x6e,
    0x67, 0x20, 0x43, 0x41, 0x30, 0x1e, 0x17, 0x0d, 0x32, 0x32, 0x30, 0x34,
    0x33, 0x30, 0x31, 0x34, 0x31, 0x36, 0x30, 0x31, 0x5a, 0x17, 0x0d, 0x34,
    0x32, 0x30, 0x34, 0x33, 0x30, 0x31, 0x34, 0x31, 0x36, 0x30, 0x31, 0x5a,
    0x30, 0x1d, 0x31, 0x1b, 0x30, 0x19, 0x06, 0x03, 0x55, 0x04, 0x03, 0x0c,
    0x12, 0x54, 0x32, 0x42, 0x31, 0x20, 0x54, 0x72, 0x65, 0x7a, 0x6f, 0x72,
    0x20, 0x53, 0x61, 0x66, 0x65, 0x20, 0x33, 0x30, 0x59, 0x30, 0x13, 0x06,
    0x07, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02, 0x01, 0x06, 0x08, 0x2a, 0x86,
    0x48, 0xce, 0x3d, 0x03, 0x01, 0x07, 0x03, 0x42, 0x00, 0x04, 0x9b, 0xbf,
    0x06, 0xda, 0xd9, 0xab, 0x59, 0x05, 0xe0, 0x54, 0x71, 0xce, 0x16, 0xd5,
    0x22, 0x2c, 0x89, 0xc2, 0xca, 0xa3, 0x9f, 0x26, 0x26, 0x7a, 0xc0, 0x74,
    0x71, 0x29, 0x88, 0x5f, 0xbd, 0x44, 0x1b, 0xcc, 0x7f, 0xa8, 0x4d, 0xe1,
    0x20, 0xa3, 0x67, 0x55, 0xda, 0xf3, 0x0a, 0x6f, 0x47, 0xe8, 0xc0, 0xd4,
    0xbd, 0xdc, 0x15, 0x03, 0x6e, 0xd2, 0xa3, 0x44, 0x7d, 0xfa, 0x7a, 0x1d,
    0x3e, 0x88, 0xa3, 0x41, 0x30, 0x3f, 0x30, 0x0e, 0x06, 0x03, 0x55, 0x1d,
    0x0f, 0x01, 0x01, 0xff, 0x04, 0x04, 0x03, 0x02, 0x00, 0x80, 0x30, 0x0c,
    0x06, 0x03, 0x55, 0x1d, 0x13, 0x01, 0x01, 0xff, 0x04, 0x02, 0x30, 0x00,
    0x30, 0x1f, 0x06, 0x03, 0x55, 0x1d, 0x23, 0x04, 0x18, 0x30, 0x16, 0x80,
    0x14, 0x67, 0xc5, 0xd4, 0xe7, 0xf0, 0x8f, 0x91, 0xb6, 0xe7, 0x48, 0xdf,
    0x42, 0xbf, 0x9f, 0x74, 0x1f, 0x43, 0xd2, 0x73, 0x75, 0x30, 0x0a, 0x06,
    0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x04, 0x03, 0x02, 0x03, 0x48, 0x00,
    0x30, 0x45, 0x02, 0x21, 0x00, 0xbe, 0x4c, 0x46, 0x8b, 0x7a, 0xdd, 0x75,
    0x77, 0xc4, 0xd9, 0xa4, 0xa7, 0xf7, 0x82, 0x6d, 0xf5, 0x33, 0x0b, 0x50,
    0x96, 0x51, 0xaf, 0x61, 0xc5, 0x76, 0xc1, 0xd0, 0x5e, 0x5e, 0x67, 0x8a,
    0x4e, 0x02, 0x20, 0x40, 0xa7, 0xdd, 0x93, 0x83, 0xa8, 0x40, 0x24, 0xc4,
    0xf9, 0xca, 0x89, 0xd9, 0x96, 0xa4, 0xf0, 0x1d, 0x7d, 0x8d, 0x37, 0xb5,
    0x0b, 0x2b, 0x98, 0x3f, 0xcc, 0x48, 0xee, 0xa4, 0x15, 0x5e, 0x55, 0x30,
    0x82, 0x01, 0xde, 0x30, 0x82, 0x01, 0x84, 0xa0, 0x03, 0x02, 0x01, 0x02,
    0x02, 0x04, 0x48, 0xf1, 0xf6, 0xc5, 0x30, 0x0a, 0x06, 0x08, 0x2a, 0x86,
    0x48, 0xce, 0x3d, 0x04, 0x03, 0x02, 0x30, 0x54, 0x31, 0x0b, 0x30, 0x09,
    0x06, 0x03, 0x55, 0x04, 0x06, 0x13, 0x02, 0x43, 0x5a, 0x31, 0x1e, 0x30,
    0x1c, 0x06, 0x03, 0x55, 0x04, 0x0a, 0x0c, 0x15, 0x54, 0x72, 0x65, 0x7a,
    0x6f, 0x72, 0x20, 0x43, 0x6f, 0x6d, 0x70, 0x61, 0x6e, 0x79, 0x20, 0x73,
    0x2e, 0x72, 0x2e, 0x6f, 0x2e, 0x31, 0x25, 0x30, 0x23, 0x06, 0x03, 0x55,
    0x04, 0x03, 0x0c, 0x1c, 0x54, 0x72, 0x65, 0x7a, 0x6f, 0x72, 0x20, 0x4d,
    0x61, 0x6e, 0x75, 0x66, 0x61, 0x63, 0x74, 0x75, 0x72, 0x69, 0x6e, 0x67,
    0x20, 0x52, 0x6f, 0x6f, 0x74, 0x20, 0x43, 0x41, 0x30, 0x20, 0x17, 0x0d,
    0x32, 0x33, 0x30, 0x31, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30,
    0x5a, 0x18, 0x0f, 0x32, 0x30, 0x35, 0x33, 0x30, 0x31, 0x30, 0x31, 0x30,
    0x30, 0x30, 0x30, 0x30, 0x30, 0x5a, 0x30, 0x4f, 0x31, 0x0b, 0x30, 0x09,
    0x06, 0x03, 0x55, 0x04, 0x06, 0x13, 0x02, 0x43, 0x5a, 0x31, 0x1e, 0x30,
    0x1c, 0x06, 0x03, 0x55, 0x04, 0x0a, 0x0c, 0x15, 0x54, 0x72, 0x65, 0x7a,
    0x6f, 0x72, 0x20, 0x43, 0x6f, 0x6d, 0x70, 0x61, 0x6e, 0x79, 0x20, 0x73,
    0x2e, 0x72, 0x2e, 0x6f, 0x2e, 0x31, 0x20, 0x30, 0x1e, 0x06, 0x03, 0x55,
    0x04, 0x03, 0x0c, 0x17, 0x54, 0x72, 0x65, 0x7a, 0x6f, 0x72, 0x20, 0x4d,
    0x61, 0x6e, 0x75, 0x66, 0x61, 0x63, 0x74, 0x75, 0x72, 0x69, 0x6e, 0x67,
    0x20, 0x43, 0x41, 0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2a, 0x86, 0x48,
    0xce, 0x3d, 0x02, 0x01, 0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03,
    0x01, 0x07, 0x03, 0x42, 0x00, 0x04, 0xba, 0x60, 0x84, 0xcb, 0x9f, 0xba,
    0x7c, 0x86, 0xd5, 0xd5, 0xa8, 0x61, 0x08, 0xa9, 0x1d, 0x55, 0xa2, 0x70,
    0x56, 0xda, 0x4e, 0xab, 0xbe, 0xdd, 0xe8, 0x8a, 0x95, 0xe1, 0xca, 0xe8,
    0xbc, 0xe3, 0x62, 0x08, 0x89, 0x16, 0x7a, 0xaf, 0x7f, 0x2d, 0xb1, 0x66,
    0x99, 0x8f, 0x95, 0x09, 0x84, 0xaa, 0x19, 0x5e, 0x86, 0x8f, 0x96, 0xe2,
    0x28, 0x03, 0xc3, 0xcd, 0x99, 0x1b, 0xe3, 0x1d, 0x39, 0xe7, 0xa3, 0x47,
    0x30, 0x45, 0x30, 0x0e, 0x06, 0x03, 0x55, 0x1d, 0x0f, 0x01, 0x01, 0xff,
    0x04, 0x04, 0x03, 0x02, 0x02, 0x04, 0x30, 0x12, 0x06, 0x03, 0x55, 0x1d,
    0x13, 0x01, 0x01, 0xff, 0x04, 0x08, 0x30, 0x06, 0x01, 0x01, 0xff, 0x02,
    0x01, 0x00, 0x30, 0x1f, 0x06, 0x03, 0x55, 0x1d, 0x23, 0x04, 0x18, 0x30,
    0x16, 0x80, 0x14, 0xc8, 0xb5, 0xb2, 0x43, 0xb3, 0x30, 0x43, 0xcc, 0x08,
    0xb4, 0xdc, 0x3a, 0x72, 0xa1, 0xde, 0xcd, 0xcf, 0xd7, 0xea, 0xdb, 0x30,
    0x0a, 0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x04, 0x03, 0x02, 0x03,
    0x48, 0x00, 0x30, 0x45, 0x02, 0x20, 0x02, 0xc1, 0x02, 0x0a, 0xb3, 0xc6,
    0x4e, 0xd9, 0xe6, 0x58, 0xfd, 0xf8, 0x70, 0x93, 0x72, 0xc9, 0xe0, 0x53,
    0x82, 0xde, 0x4e, 0x58, 0x75, 0x80, 0xc8, 0xba, 0xc4, 0x2f, 0x43, 0x78,
    0x4a, 0xd9, 0x02, 0x21, 0x00, 0x99, 0x00, 0x98, 0x1c, 0xbc, 0x68, 0xae,
    0xb0, 0x6d, 0x3e, 0xa9, 0x11, 0x94, 0x8d, 0x63, 0x11, 0xd6, 0xf6, 0x94,
    0x40, 0x3a, 0xbb, 0xbb, 0x65, 0x9e, 0x5a, 0xf5, 0x2b, 0xf3, 0x2e, 0x33,
    0xc4};

int optiga_sign(uint8_t index, const uint8_t *digest, size_t digest_size,
                uint8_t *signature, size_t max_sig_size, size_t *sig_size) {
  const uint8_t DEVICE_PRIV_KEY[32] = {1};

  if (index != OPTIGA_DEVICE_ECC_KEY_INDEX) {
    return false;
  }

  if (max_sig_size < 72) {
    return OPTIGA_ERR_SIZE;
  }

  uint8_t raw_signature[64] = {0};
  int ret = ecdsa_sign_digest(&nist256p1, DEVICE_PRIV_KEY, digest,
                              raw_signature, NULL, NULL);
  if (ret != 0) {
    return OPTIGA_ERR_CMD;
  }

  *sig_size = ecdsa_sig_to_der(raw_signature, signature);
  return OPTIGA_SUCCESS;
}

bool optiga_cert_size(uint8_t index, size_t *cert_size) {
  if (index != OPTIGA_DEVICE_CERT_INDEX) {
    return false;
  }

  *cert_size = sizeof(DEVICE_CERT_CHAIN);
  return true;
}

bool optiga_read_cert(uint8_t index, uint8_t *cert, size_t max_cert_size,
                      size_t *cert_size) {
  if (index != OPTIGA_DEVICE_CERT_INDEX) {
    return false;
  }

  if (max_cert_size < sizeof(DEVICE_CERT_CHAIN)) {
    return false;
  }

  memcpy(cert, DEVICE_CERT_CHAIN, sizeof(DEVICE_CERT_CHAIN));
  *cert_size = sizeof(DEVICE_CERT_CHAIN);
  return true;
}

bool optiga_random_buffer(uint8_t *dest, size_t size) {
  random_buffer(dest, size);
  return true;
}

int optiga_pin_set(OPTIGA_UI_PROGRESS ui_progress,
                   const uint8_t pin_secret[OPTIGA_PIN_SECRET_SIZE],
                   uint8_t out_secret[OPTIGA_PIN_SECRET_SIZE]) {
  memcpy(out_secret, pin_secret, OPTIGA_PIN_SECRET_SIZE);
  ui_progress(OPTIGA_PIN_DERIVE_MS);
  return OPTIGA_SUCCESS;
}

int optiga_pin_verify(OPTIGA_UI_PROGRESS ui_progress,
                      const uint8_t pin_secret[OPTIGA_PIN_SECRET_SIZE],
                      uint8_t out_secret[OPTIGA_PIN_SECRET_SIZE]) {
  memcpy(out_secret, pin_secret, OPTIGA_PIN_SECRET_SIZE);
  ui_progress(OPTIGA_PIN_DERIVE_MS);
  return OPTIGA_SUCCESS;
}

int optiga_pin_get_fails(uint32_t *ctr) {
  *ctr = 0;
  return OPTIGA_SUCCESS;
}

int optiga_pin_fails_increase(uint32_t count) { return OPTIGA_SUCCESS; }
