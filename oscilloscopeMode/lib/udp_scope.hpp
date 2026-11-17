// SPDX-License-Identifier: GPL-3.0-or-later
//
// Copyright (C) 2026 Daniel Batista, Thalles Campagnani
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

#ifndef UDP_SCOPE_HPP
#define UDP_SCOPE_HPP

#include <cstdint>
#include <cstddef>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct UdpScope UdpScope;

UdpScope *udp_scope_create(void);
void      udp_scope_destroy(UdpScope *s);

void udp_scope_set_bind(UdpScope *s, const char *addr);
void udp_scope_set_port(UdpScope *s, int port);
void udp_scope_set_sample_rate(UdpScope *s, double hz);
void udp_scope_set_bits(UdpScope *s, int bits);
void udp_scope_set_v_range(UdpScope *s, double volts);
void udp_scope_set_out_path(UdpScope *s, const char *path);
void udp_scope_set_csv_path(UdpScope *s, const char *path); /* alias of out_path */
/* "csv" (default) or "int16" / "i16" / "raw": packed 12/14-bit → little-endian int16 */
void udp_scope_set_format(UdpScope *s, const char *fmt);
void udp_scope_set_max_samples(UdpScope *s, uint64_t n);
void udp_scope_request_stop(UdpScope *s);

/* Blocking. 0 = ok, <0 = error. */
int udp_scope_run(UdpScope *s);

uint64_t udp_scope_samples_written(const UdpScope *s);
uint64_t udp_scope_packets(const UdpScope *s);
uint64_t udp_scope_gaps(const UdpScope *s);
const char *udp_scope_last_error(const UdpScope *s);

#ifdef __cplusplus
}
#endif

#endif
