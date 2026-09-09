# gpraw — GPRaw MOV container reader/writer + pack/unpack CLI tools.
#
# Builds against Homebrew FFmpeg (libavformat + libavutil). Tested with
# FFmpeg 8.0.1 / lavf 62.3 / lavu 60.8 on macOS arm64.

CC      ?= clang
PKG     ?= pkg-config
AV_CFLAGS  := $(shell $(PKG) --cflags libavformat libavutil)
AV_LDLIBS  := $(shell $(PKG) --libs   libavformat libavutil)

CFLAGS  := -O2 -g -Wall -Wextra -Wno-unused-parameter -std=c11 \
           -Iinclude $(AV_CFLAGS)
LDLIBS  := $(AV_LDLIBS)

OBJDIR   = build

LIB_OBJS    = $(OBJDIR)/gpraw.o
PACK_OBJS   = $(OBJDIR)/gpraw_pack.o   $(LIB_OBJS)
UNPACK_OBJS = $(OBJDIR)/gpraw_unpack.o $(LIB_OBJS)

BINS = gpraw_pack gpraw_unpack

.PHONY: all clean
all: $(BINS)

$(OBJDIR):
	mkdir -p $(OBJDIR)

$(OBJDIR)/%.o: src/%.c | $(OBJDIR)
	$(CC) $(CFLAGS) -c $< -o $@

gpraw_pack: $(PACK_OBJS)
	$(CC) $(CFLAGS) $^ $(LDLIBS) -o $@

gpraw_unpack: $(UNPACK_OBJS)
	$(CC) $(CFLAGS) $^ $(LDLIBS) -o $@

clean:
	rm -rf $(OBJDIR) $(BINS)
