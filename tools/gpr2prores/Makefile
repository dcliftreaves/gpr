# Makefile for gpr2prores

GPR_BUILD = ../../build-local

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
          -framework CoreMedia \
          -framework VideoToolbox \
          -framework AVFoundation \
          -framework CoreML

GPR_LIBS = $(GPR_BUILD)/source/lib/vc5_encoder/libvc5_encoder.a \
           $(GPR_BUILD)/source/lib/vc5_decoder/libvc5_decoder.a \
           $(GPR_BUILD)/source/lib/vc5_common/libvc5_common.a \
           $(GPR_BUILD)/source/lib/common/libcommon.a

OBJS = gpr2prores.o DNGReader.o GPRFileReader.o GPRPipeline.o Demosaic.o ProResWriter.o GPRCodec.o SuperResCNN.o SuperResMetal.o

FFMPEG_LIBS = -lavformat -lavcodec -lavutil -lswresample

.PHONY: all clean

all: gpr2prores gpr_mov_tool

gpr2prores: $(OBJS) Demosaic.metallib
	$(CC) $(OBJS) $(GPR_LIBS) $(LDFLAGS) -o $@

# gpr_mov_tool: pack/unpack a sequence of .gpr files into a custom-tagged MOV.
gpr_mov_tool: gpr_mov_tool.o GPRMovWriter.o GPRMovReader.o GPRFileReader.o
	$(CC) $^ $(LDFLAGS) $(FFMPEG_LIBS) -o $@

%.o: %.m
	$(CC) $(CFLAGS) -c $< -o $@

# Build Metal library next to binary so MTLDevice newDefaultLibrary can find it.
# Compile each .metal to .air, then link all into default.metallib.
Demosaic.metallib: Demosaic.metal SuperResPost.metal NAFBlockKernels_LNConv.metal NAFBlockKernels_DWGateProjRes.metal NAFBlockKernels_GateProjRes.metal
	xcrun -sdk macosx metal -c Demosaic.metal -o Demosaic.air
	xcrun -sdk macosx metal -c SuperResPost.metal -o SuperResPost.air
	xcrun -sdk macosx metal -c NAFBlockKernels_LNConv.metal -o NAFBlockKernels_LNConv.air
	xcrun -sdk macosx metal -c NAFBlockKernels_DWGateProjRes.metal -o NAFBlockKernels_DWGateProjRes.air
	xcrun -sdk macosx metal -c NAFBlockKernels_GateProjRes.metal -o NAFBlockKernels_GateProjRes.air
	xcrun -sdk macosx metallib Demosaic.air SuperResPost.air NAFBlockKernels_LNConv.air NAFBlockKernels_DWGateProjRes.air NAFBlockKernels_GateProjRes.air -o default.metallib
	cp default.metallib Demosaic.metallib

clean:
	rm -f $(OBJS) gpr2prores *.air *.metallib
