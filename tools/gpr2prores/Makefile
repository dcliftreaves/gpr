# Makefile for gpr2prores

GPR_BUILD = ../../build-local
PREFIX    ?= /usr/local
BINDIR    = $(PREFIX)/bin
LIBDIR    = $(PREFIX)/lib/gpr2prores

# Sanity check: $(GPR_BUILD) MUST be configured Release (or RelWithDebInfo),
# otherwise the decoder links against an -O0 libvc5_decoder.a and decode
# runs ~6× slower (63 ms vs 10 ms on M3 Max for half-res UHD), capping
# playback at ~15 fps instead of ~27 fps. The root CMakeLists.txt now
# defaults to Release when no build type is given, but an old
# CMakeCache.txt with CMAKE_BUILD_TYPE="" survives reconfigures, so we
# check explicitly here. To fix: `cmake -B $(GPR_BUILD) -DCMAKE_BUILD_TYPE=Release`.
BUILD_TYPE := $(shell grep '^CMAKE_BUILD_TYPE:' $(GPR_BUILD)/CMakeCache.txt 2>/dev/null | cut -d'=' -f2)
ifeq ($(BUILD_TYPE),)
    $(warning $(GPR_BUILD)/CMakeCache.txt has empty CMAKE_BUILD_TYPE — libs likely built at -O0)
    $(warning Reconfigure with: cmake -B $(GPR_BUILD) -DCMAKE_BUILD_TYPE=Release && cmake --build $(GPR_BUILD) -j8)
endif

CC      = clang
CFLAGS  = -O2 -g -Wall -Wno-deprecated-declarations -fobjc-arc \
          -I$(GPR_BUILD)/../source/lib/vc5_encoder \
          -I$(GPR_BUILD)/../source/lib/vc5_decoder \
          -I/opt/homebrew/include \
          -DGPR_HAVE_SUPER_RES_METAL=1 \
          -mmacosx-version-min=14.0

LDFLAGS = -L/opt/homebrew/lib -lraw -lc++ \
          -framework Accelerate \
          -framework Foundation \
          -framework CoreFoundation \
          -framework CoreGraphics \
          -framework ImageIO \
          -framework CoreServices \
          -framework Metal \
          -framework MetalKit \
          -framework MetalPerformanceShaders \
          -framework MetalPerformanceShadersGraph \
          -framework CoreImage \
          -framework CoreVideo \
          -framework IOSurface \
          -framework CoreMedia \
          -framework VideoToolbox \
          -framework AVFoundation \
          -framework CoreML

GPR_LIBS = $(GPR_BUILD)/source/lib/vc5_encoder/libvc5_encoder.a \
           $(GPR_BUILD)/source/lib/vc5_decoder/libvc5_decoder.a \
           $(GPR_BUILD)/source/lib/vc5_common/libvc5_common.a \
           $(GPR_BUILD)/source/lib/common/libcommon.a

OBJS = gpr2prores.o DNGReader.o GPRFileReader.o GPRPipeline.o Demosaic.o Downscale.o CIRawDemosaic.o CIDNGBuilder.o ProResWriter.o GPRCodec.o SuperResCNN.o SuperResMetal.o

FFMPEG_LIBS = -lavformat -lavcodec -lavutil -lswresample

.PHONY: all clean install uninstall

all: gpr2prores gpr_mov_tool

gpr2prores: $(OBJS) Demosaic.metallib
	$(CC) $(OBJS) $(GPR_LIBS) $(LDFLAGS) -o $@

# gpr_mov_tool: pack/unpack a sequence of .gpr files into a custom-tagged MOV.
gpr_mov_tool: gpr_mov_tool.o GPRMovWriter.o GPRMovReader.o GPRFileReader.o DNGExif.o
	$(CC) $^ $(LDFLAGS) $(FFMPEG_LIBS) -o $@

%.o: %.m
	$(CC) $(CFLAGS) -c $< -o $@

# Build Metal library next to binary so MTLDevice newDefaultLibrary can find it.
# Compile each .metal to .air, then link all into default.metallib.
Demosaic.metallib: Demosaic.metal SuperResPost.metal Downscale.metal NAFBlockKernels_LNConv.metal NAFBlockKernels_DWGateProjRes.metal NAFBlockKernels_GateProjRes.metal NAFBlockKernels_ANE_Conv1x1.metal NAFBlockKernels_ANE_DWSiLUProjRes.metal NAFBlockKernels_ANE_SiLUProjRes.metal
	xcrun -sdk macosx metal -c Demosaic.metal -o Demosaic.air
	xcrun -sdk macosx metal -c SuperResPost.metal -o SuperResPost.air
	xcrun -sdk macosx metal -c Downscale.metal -o Downscale.air
	xcrun -sdk macosx metal -c NAFBlockKernels_LNConv.metal -o NAFBlockKernels_LNConv.air
	xcrun -sdk macosx metal -c NAFBlockKernels_DWGateProjRes.metal -o NAFBlockKernels_DWGateProjRes.air
	xcrun -sdk macosx metal -c NAFBlockKernels_GateProjRes.metal -o NAFBlockKernels_GateProjRes.air
	xcrun -sdk macosx metal -c NAFBlockKernels_ANE_Conv1x1.metal -o NAFBlockKernels_ANE_Conv1x1.air
	xcrun -sdk macosx metal -c NAFBlockKernels_ANE_DWSiLUProjRes.metal -o NAFBlockKernels_ANE_DWSiLUProjRes.air
	xcrun -sdk macosx metal -c NAFBlockKernels_ANE_SiLUProjRes.metal -o NAFBlockKernels_ANE_SiLUProjRes.air
	xcrun -sdk macosx metallib Demosaic.air SuperResPost.air Downscale.air NAFBlockKernels_LNConv.air NAFBlockKernels_DWGateProjRes.air NAFBlockKernels_GateProjRes.air NAFBlockKernels_ANE_Conv1x1.air NAFBlockKernels_ANE_DWSiLUProjRes.air NAFBlockKernels_ANE_SiLUProjRes.air -o default.metallib
	cp default.metallib Demosaic.metallib

clean:
	rm -f $(OBJS) gpr2prores gpr_mov_tool *.o *.air *.metallib

# Install gpr2prores + gpr_mov_tool into $(BINDIR) and metallibs into $(LIBDIR).
# Set PREFIX to relocate (default /usr/local). Requires sudo for /usr/local.
# Symlink the metallib next to the binary so gpr2prores can find it without
# changing its search code.
install: gpr2prores gpr_mov_tool Demosaic.metallib
	@echo "Installing to $(PREFIX)"
	install -d "$(BINDIR)"
	install -d "$(LIBDIR)"
	install -m 0755 gpr2prores "$(BINDIR)/gpr2prores"
	install -m 0755 gpr_mov_tool "$(BINDIR)/gpr_mov_tool"
	install -m 0644 default.metallib "$(LIBDIR)/default.metallib"
	install -m 0644 Demosaic.metallib "$(LIBDIR)/Demosaic.metallib"
	ln -sf "$(LIBDIR)/default.metallib" "$(BINDIR)/default.metallib"
	ln -sf "$(LIBDIR)/Demosaic.metallib" "$(BINDIR)/Demosaic.metallib"
	@echo "Installed:"
	@echo "  $(BINDIR)/gpr2prores"
	@echo "  $(BINDIR)/gpr_mov_tool"
	@echo "  $(LIBDIR)/default.metallib (linked into BINDIR)"

uninstall:
	rm -f "$(BINDIR)/gpr2prores" "$(BINDIR)/gpr_mov_tool"
	rm -f "$(BINDIR)/default.metallib" "$(BINDIR)/Demosaic.metallib"
	rm -rf "$(LIBDIR)"
