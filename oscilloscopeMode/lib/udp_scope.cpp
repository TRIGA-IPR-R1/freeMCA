// SPDX-License-Identifier: GPL-3.0-or-later
//
// Copyright (C) 2026 Daniel Batista, Thalles Campagnani
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

#include "udp_scope.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <new>
#include <string>
#include <vector>

namespace {

constexpr uint16_t kMagic = 0xADC0;
constexpr uint16_t kFlagPacked = 2;
constexpr uint16_t kFlagOffset = 4;
constexpr int kHdrLen = 10;
constexpr int kMaxPkt = 4096;

uint16_t u16le(const uint8_t *p) {
    return static_cast<uint16_t>(p[0] | (p[1] << 8));
}

uint32_t u32le(const uint8_t *p) {
    return static_cast<uint32_t>(p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24));
}

}  // namespace

enum class OutFormat { Csv, Int16 };

struct UdpScope {
    std::string bind{"0.0.0.0"};
    int port{5000};
    double sample_rate{31.25e6};
    int bits{14};
    double v_range{5.0};
    std::string out_path{"capture.csv"};
    OutFormat format{OutFormat::Csv};
    uint64_t max_samples{0};

    std::atomic<bool> stop{false};
    std::atomic<uint64_t> samples_written{0};
    std::atomic<uint64_t> packets{0};
    std::atomic<uint64_t> gaps{0};
    std::string last_error;

    bool unpack_packed(const uint8_t *buf, int nbytes, int n, int bits, bool offset,
                       std::vector<int32_t> *out) const {
        out->resize(static_cast<size_t>(n));
        uint64_t acc = 0;
        int nbits = 0;
        int i = 0;
        const uint32_t mask = (1u << bits) - 1u;
        const int32_t sign = 1 << (bits - 1);
        const int32_t ext = 1 << bits;
        for (int k = 0; k < n; ++k) {
            while (nbits < bits) {
                if (i >= nbytes)
                    return false;
                acc |= static_cast<uint64_t>(buf[i]) << nbits;
                nbits += 8;
                ++i;
            }
            int32_t s = static_cast<int32_t>(acc & mask);
            acc >>= bits;
            nbits -= bits;
            if (offset)
                s -= sign;
            else if (s >= sign)
                s -= ext;
            (*out)[static_cast<size_t>(k)] = s;
        }
        return true;
    }

    double to_volt(int32_t signed_code) const {
        const int mid = 1 << (bits - 1);
        return (static_cast<double>(signed_code) / static_cast<double>(mid)) * v_range;
    }
};

namespace {

std::atomic<UdpScope *> g_running{nullptr};

void on_sigint(int) {
    UdpScope *s = g_running.load();
    if (s)
        s->stop.store(true);
}

}  // namespace

extern "C" UdpScope *udp_scope_create(void) {
    return new UdpScope();
}

extern "C" void udp_scope_destroy(UdpScope *s) {
    delete s;
}

extern "C" void udp_scope_set_bind(UdpScope *s, const char *addr) {
    if (s && addr)
        s->bind = addr;
}

extern "C" void udp_scope_set_port(UdpScope *s, int port) {
    if (s)
        s->port = port;
}

extern "C" void udp_scope_set_sample_rate(UdpScope *s, double hz) {
    if (s && hz > 0.0)
        s->sample_rate = hz;
}

extern "C" void udp_scope_set_bits(UdpScope *s, int bits) {
    if (s && bits >= 1 && bits <= 16)
        s->bits = bits;
}

extern "C" void udp_scope_set_v_range(UdpScope *s, double volts) {
    if (s && volts > 0.0)
        s->v_range = volts;
}

extern "C" void udp_scope_set_out_path(UdpScope *s, const char *path) {
    if (s && path)
        s->out_path = path;
}

extern "C" void udp_scope_set_csv_path(UdpScope *s, const char *path) {
    udp_scope_set_out_path(s, path);
}

extern "C" void udp_scope_set_format(UdpScope *s, const char *fmt) {
    if (!s || !fmt)
        return;
    if (std::strcmp(fmt, "int16") == 0 || std::strcmp(fmt, "i16") == 0 ||
        std::strcmp(fmt, "raw") == 0)
        s->format = OutFormat::Int16;
    else
        s->format = OutFormat::Csv;
}

extern "C" void udp_scope_set_max_samples(UdpScope *s, uint64_t n) {
    if (s)
        s->max_samples = n;
}

extern "C" void udp_scope_request_stop(UdpScope *s) {
    if (s)
        s->stop.store(true);
}

extern "C" uint64_t udp_scope_samples_written(const UdpScope *s) {
    return s ? s->samples_written.load() : 0;
}

extern "C" uint64_t udp_scope_packets(const UdpScope *s) {
    return s ? s->packets.load() : 0;
}

extern "C" uint64_t udp_scope_gaps(const UdpScope *s) {
    return s ? s->gaps.load() : 0;
}

extern "C" const char *udp_scope_last_error(const UdpScope *s) {
    return s ? s->last_error.c_str() : "null";
}

extern "C" int udp_scope_run(UdpScope *s) {
    if (!s)
        return -1;
    s->stop.store(false);
    s->samples_written.store(0);
    s->packets.store(0);
    s->gaps.store(0);
    s->last_error.clear();
    g_running.store(s);
    std::signal(SIGINT, on_sigint);

    int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        s->last_error = std::strerror(errno);
        return -1;
    }
    int yes = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
    int rcv = 32 * 1024 * 1024;
    setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &rcv, sizeof(rcv));

    timeval tv{};
    tv.tv_sec = 0;
    tv.tv_usec = 200000;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<uint16_t>(s->port));
    if (inet_pton(AF_INET, s->bind.c_str(), &addr.sin_addr) != 1)
        addr.sin_addr.s_addr = htonl(INADDR_ANY);

    if (bind(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) != 0) {
        s->last_error = std::strerror(errno);
        close(fd);
        return -1;
    }

    const bool raw_i16 = s->format == OutFormat::Int16;
    FILE *out = std::fopen(s->out_path.c_str(), raw_i16 ? "wb" : "w");
    if (!out) {
        s->last_error = std::strerror(errno);
        close(fd);
        return -1;
    }
    std::setvbuf(out, nullptr, _IOFBF, 1 << 20);
    if (!raw_i16)
        std::fputs("t_s,v\n", out);

    const double dt = 1.0 / s->sample_rate;
    std::vector<int32_t> samp;
    samp.reserve(720);
    std::vector<int16_t> i16pkt;

    // Buffer the window in RAM, then write. fprintf/fwrite at 31 MSPS drops UDP.
    const bool buffered = s->max_samples > 0;
    std::vector<uint64_t> t_idx;
    std::vector<int32_t> codes;
    std::vector<int16_t> i16buf;
    if (buffered) {
        try {
            if (raw_i16)
                i16buf.reserve(s->max_samples);
            else {
                t_idx.reserve(s->max_samples);
                codes.reserve(s->max_samples);
            }
        } catch (const std::bad_alloc &) {
            s->last_error = "out of memory (reduce --samples)";
            std::fclose(out);
            close(fd);
            g_running.store(nullptr);
            return -1;
        }
    }

    bool have_origin = false;
    uint32_t seq0 = 0;
    uint16_t n0 = 720;
    uint32_t last_seq = 0;
    uint8_t pkt[kMaxPkt];

    while (!s->stop.load()) {
        if (s->max_samples > 0 && s->samples_written.load() >= s->max_samples)
            break;

        sockaddr_in src{};
        socklen_t slen = sizeof(src);
        ssize_t nread = recvfrom(fd, pkt, sizeof(pkt), 0, reinterpret_cast<sockaddr *>(&src), &slen);
        if (nread < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)
                continue;
            s->last_error = std::strerror(errno);
            break;
        }
        if (nread < kHdrLen)
            continue;
        if (u16le(pkt) != kMagic)
            continue;

        const uint32_t seq = u32le(pkt + 2);
        const uint16_t n = u16le(pkt + 6);
        const uint16_t flags = u16le(pkt + 8);
        if (n == 0)
            continue;

        const uint8_t *payload = pkt + kHdrLen;
        const int paylen = static_cast<int>(nread) - kHdrLen;
        bool ok = false;
        if (flags & kFlagPacked) {
            const int bits = (paylen * 8) / n;
            if (bits >= 1 && bits <= 16) {
                const int need = (n * bits + 7) / 8;
                if (paylen >= need)
                    ok = s->unpack_packed(payload, need, n, bits, flags & kFlagOffset, &samp);
            }
        } else {
            if (paylen >= n * 2) {
                samp.resize(n);
                for (int i = 0; i < n; ++i) {
                    int16_t v = static_cast<int16_t>(u16le(payload + 2 * i));
                    samp[static_cast<size_t>(i)] = v;
                }
                ok = true;
            }
        }
        if (!ok)
            continue;

        if (!have_origin) {
            have_origin = true;
            seq0 = seq;
            n0 = n;
            last_seq = seq;
        } else {
            const uint32_t expect = last_seq + 1;
            if (seq != expect)
                s->gaps.fetch_add(1);
            last_seq = seq;
        }

        const uint64_t base = static_cast<uint64_t>(seq - seq0) * static_cast<uint64_t>(n0);
        const int remain = (s->max_samples > 0)
                               ? static_cast<int>(std::min<uint64_t>(n, s->max_samples - s->samples_written.load()))
                               : n;
        if (raw_i16) {
            if (buffered) {
                for (int i = 0; i < remain; ++i)
                    i16buf.push_back(static_cast<int16_t>(samp[static_cast<size_t>(i)]));
            } else {
                i16pkt.resize(static_cast<size_t>(remain));
                for (int i = 0; i < remain; ++i)
                    i16pkt[static_cast<size_t>(i)] =
                        static_cast<int16_t>(samp[static_cast<size_t>(i)]);
                std::fwrite(i16pkt.data(), sizeof(int16_t), static_cast<size_t>(remain), out);
            }
        } else if (buffered) {
            for (int i = 0; i < remain; ++i) {
                t_idx.push_back(base + static_cast<uint64_t>(i));
                codes.push_back(samp[static_cast<size_t>(i)]);
            }
        } else {
            for (int i = 0; i < remain; ++i) {
                const double t = static_cast<double>(base + static_cast<uint64_t>(i)) * dt;
                const double v = s->to_volt(samp[static_cast<size_t>(i)]);
                std::fprintf(out, "%.10E,%.8E\n", t, v);
            }
        }
        s->samples_written.fetch_add(static_cast<uint64_t>(remain));
        s->packets.fetch_add(1);
    }

    if (buffered) {
        if (raw_i16) {
            if (!i16buf.empty())
                std::fwrite(i16buf.data(), sizeof(int16_t), i16buf.size(), out);
        } else {
            for (size_t i = 0; i < codes.size(); ++i) {
                const double t = static_cast<double>(t_idx[i]) * dt;
                const double v = s->to_volt(codes[i]);
                std::fprintf(out, "%.10E,%.8E\n", t, v);
            }
        }
    }

    std::fclose(out);
    close(fd);
    g_running.store(nullptr);
    return s->last_error.empty() ? 0 : -1;
}
