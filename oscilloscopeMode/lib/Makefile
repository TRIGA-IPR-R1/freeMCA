# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copyright (C) 2026 Daniel Batista, Thalles Campagnani

CXX      ?= g++
CXXFLAGS ?= -O3 -std=c++17 -fPIC -Wall -Wextra
LDFLAGS  ?= -shared

LIB = libudp_scope.so

.PHONY: all clean

all: $(LIB)

$(LIB): udp_scope.cpp udp_scope.hpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ udp_scope.cpp

clean:
	rm -f $(LIB) *.o
