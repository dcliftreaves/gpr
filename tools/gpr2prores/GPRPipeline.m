// GPRPipeline.m — orchestrates {DNG | GPR} → [codec] → CNN → demosaic → ProRes.
//
// 4-deep frame pipeline:
//   [reader_queue]    read+decode -> bayer plane (sem-gated cnn_inbox, N=2 free slots)
//   [cnn_queue]       CNN super-res         (sem-gated demosaic_inbox, N=2)
//   [demosaic_queue]  demosaic + ProRes pb  (sem-gated writer_inbox,   N=4)
//   [writer_queue]    AVAssetWriter append in PTS order
//
// Main thread submits all frame jobs, waits on a final "all done" semaphore.
//
// Stage-internal state (CNN's persistent MTLBuffers, Demosaic's _bayerBuf,
// the GPR codec's encoder context) is shared and not thread-safe — each
// stage's queue is serial, so only one frame is processed at a time within a
// stage. Inter-stage overlap is what gives us the throughput speedup.
//
// AVAssetWriter requires frames in PTS order. The writer queue maintains a
// frame-tag dictionary and writes the next sequential frame whenever its tag
// arrives, holding higher-tagged frames in memory until predecessors land.

#import "GPRPipeline.h"
#import "DNGReader.h"
#import "GPRFileReader.h"
#import "Demosaic.h"
#import "ProResWriter.h"
#import "GPRCodec.h"
#import "SuperResCNN.h"
#import "SuperResMetal.h"

#import <Metal/Metal.h>
#import <CoreVideo/CoreVideo.h>
#import <mach/mach_time.h>
#import <stdatomic.h>

static double now_ms(void) {
    static mach_timebase_info_data_t tb = {0};
    if (tb.denom == 0) mach_timebase_info(&tb);
    return (double)mach_absolute_time() * tb.numer / tb.denom / 1.0e6;
}

static BOOL pathIsGPR(NSString *p) {
    return [[p.lowercaseString pathExtension] isEqualToString:@"gpr"];
}

// Per-frame job moving through the pipeline. The bayer pointers are owned by
// the job and freed by whoever last touches them (the producer of the next
// buffer when it no longer needs the previous, or the writer at the end).
@interface FrameJob : NSObject
@property (nonatomic, assign) int idx;          // 0-based frame index (PTS order)
@property (nonatomic, copy)   NSString *path;   // for logging
@property (nonatomic, assign) double t_submit;
@property (nonatomic, assign) double t_read;
@property (nonatomic, assign) double t_decode;
@property (nonatomic, assign) double t_cnn;
@property (nonatomic, assign) double t_demosaic;
@property (nonatomic, assign) double t_write;
// Bayer buffer the next stage consumes. The size and meaning depends on the
// stage: after read+decode it's the decoded-bayer buffer (codec dims), after
// CNN it's native-dim bayer.
@property (nonatomic, assign) uint16_t *bayer;
@property (nonatomic, assign) uint32_t bayerW;
@property (nonatomic, assign) uint32_t bayerH;
@property (nonatomic, assign) BOOL bayerOwned;  // YES = free() on consume
// Optional: a CVPixelBuffer the demosaic stage materialized. Retained from
// pool until appended.
@property (nonatomic, assign) CVPixelBufferRef pb;
@end

@implementation FrameJob
- (void)dealloc {
    if (_bayer && _bayerOwned) { free(_bayer); _bayer = NULL; }
    if (_pb) { CVPixelBufferRelease(_pb); _pb = NULL; }
}
@end

// Simple FIFO inbox: serial dispatch_queue + dispatch_semaphore for backpressure.
// Producers wait on `slots` before posting; consumers `signal` slots when done.
@interface StageInbox : NSObject
@property (nonatomic, strong) dispatch_queue_t queue;
@property (nonatomic, strong) dispatch_semaphore_t slots;  // available slots
@end
@implementation StageInbox
@end

static StageInbox *make_inbox(const char *label, int capacity) {
    StageInbox *b = [[StageInbox alloc] init];
    b.queue = dispatch_queue_create(label, DISPATCH_QUEUE_SERIAL);
    b.slots = dispatch_semaphore_create(capacity);
    return b;
}

@interface GPRPipeline () {
    NSString *_ckptPath;
    NSString *_outPath;
    int _fps;
    BOOL _aaOn;
    BOOL _noCNN;
    BOOL _noCodec;
    BOOL _timing;
    BOOL _gprInput;
    NSString *_cnnBackend;

    DNGInfo _info;
    DNGInfo _codecInfo;
    DNGInfo _cnnInfo;

    id<MTLDevice> _device;
    id<MTLCommandQueue> _queue;
    Demosaic *_demosaic;
    ProResWriter *_writer;
    GPRCodec *_codec;
    SuperResCNN *_cnn;
    SuperResMetal *_cnnMetal;

    // Reorder buffer for writer (frames may finish demosaic out of order).
    NSMutableDictionary<NSNumber *, FrameJob *> *_writePending;
    int _nextWriteIdx;
    NSLock *_writeLock;
}
@end

@implementation GPRPipeline

- (nullable instancetype)initWithFirstFrame:(NSString *)firstFrame
                                metaDngPath:(nullable NSString *)metaDngPath
                                   ckptPath:(NSString *)ckptPath
                                    outPath:(NSString *)outPath
                                        fps:(int)fps
                                       aaOn:(BOOL)aaOn
                                      noCNN:(BOOL)noCNN
                                    noCodec:(BOOL)noCodec
                                     timing:(BOOL)timing
                                 cnnBackend:(NSString *)cnnBackend
{
    self = [super init];
    if (!self) return nil;
    _ckptPath = ckptPath;
    _outPath = outPath;
    _fps = fps;
    _aaOn = aaOn;
    _noCNN = noCNN;
    _noCodec = noCodec;
    _timing = timing;
    _gprInput = pathIsGPR(firstFrame);
    _cnnBackend = cnnBackend ?: @"coreml";

    if (_gprInput) {
        if (!metaDngPath) {
            fprintf(stderr, "GPRPipeline: GPR input requires --meta-dng <path-to-source-DNG>\n");
            return nil;
        }
        uint16_t *bayer = [DNGReader readBayerFromPath:metaDngPath info:&_info];
        if (!bayer) {
            fprintf(stderr, "GPRPipeline: cannot read metaDng %s\n", [metaDngPath UTF8String]);
            return nil;
        }
        free(bayer);

        GPRFileInfo gi = {0};
        if (![GPRFileReader readHeaderFromPath:firstFrame info:&gi]) {
            fprintf(stderr, "GPRPipeline: bad header in %s\n", [firstFrame UTF8String]);
            return nil;
        }
        _info.width  = gi.encWidth;
        _info.height = gi.encHeight;
        _noCodec = YES;
        _codecInfo = _info;
        _codecInfo.width  = gi.decWidth;
        _codecInfo.height = gi.decHeight;
        fprintf(stderr, "GPRPipeline: GPR input %ux%u → decoded %ux%u (decimate=%u)\n",
                gi.encWidth, gi.encHeight, gi.decWidth, gi.decHeight, gi.decimate);
    } else {
        uint16_t *bayer = [DNGReader readBayerFromPath:firstFrame info:&_info];
        if (!bayer) {
            fprintf(stderr, "GPRPipeline: cannot read first frame %s\n", [firstFrame UTF8String]);
            return nil;
        }
        free(bayer);
        _codecInfo = _info;
        _codecInfo.width  = _info.width  / 2;
        _codecInfo.height = _info.height / 2;
    }
    _cnnInfo = _info;

    uint32_t demoW = _info.width, demoH = _info.height;
    if (_gprInput) {
        if (_noCNN) { demoW = _codecInfo.width; demoH = _codecInfo.height; }
        else        { demoW = _info.width;      demoH = _info.height; }
    } else if (_noCodec || !_noCNN) {
        demoW = _info.width;
        demoH = _info.height;
    } else {
        demoW = _codecInfo.width;
        demoH = _codecInfo.height;
    }

    _device = MTLCreateSystemDefaultDevice();
    if (!_device) { fprintf(stderr, "no Metal device\n"); return nil; }
    _queue = [_device newCommandQueue];

    _demosaic = [[Demosaic alloc] initWithDevice:_device
                                    width:demoW
                                   height:demoH
                              cfaPattern:_info.cfaPattern
                              blackLevel:_info.blackLevel
                              whiteLevel:_info.whiteLevel
                                     wbR:_info.wbR
                                     wbG:_info.wbG
                                     wbB:_info.wbB
                                  rgbCam:_info.rgb_cam];
    if (!_demosaic) { fprintf(stderr, "demosaic init failed\n"); return nil; }

    _writer = [[ProResWriter alloc] initWithPath:_outPath
                                            width:demoW
                                           height:demoH
                                              fps:_fps
                                           device:_device];
    if (!_writer) { fprintf(stderr, "writer init failed\n"); return nil; }

    if (!_noCodec) {
        setenv("GPR_INCLUDE_LL", "1", 1);
        setenv("GPR_ROW_DECIMATE", "2", 1);
        setenv("GPR_COL_DECIMATE", "2", 1);
        setenv("GPR_DROP_HIGHPASS", "1", 1);
        if (_aaOn) setenv("GPR_DECIMATE_AA", "1", 1);
        else       unsetenv("GPR_DECIMATE_AA");

        int pixel_format;
        if (_info.cfaPattern == 0) pixel_format = (_info.whiteLevel > 16383) ? 4 : 1;
        else                       pixel_format = (_info.whiteLevel > 16383) ? 5 : 3;
        _codec = [[GPRCodec alloc] initWithWidth:_info.width
                                          height:_info.height
                                    pixelFormat:pixel_format
                                        quality:3];
        if (!_codec) { fprintf(stderr, "codec init failed\n"); return nil; }
    } else if (_gprInput) {
        int pixel_format;
        if (_info.cfaPattern == 0) pixel_format = (_info.whiteLevel > 16383) ? 4 : 1;
        else                       pixel_format = (_info.whiteLevel > 16383) ? 5 : 3;
        _codec = [[GPRCodec alloc] initWithWidth:_info.width
                                          height:_info.height
                                    pixelFormat:pixel_format
                                        quality:3];
    }

    if (!_noCNN) {
        if ([_cnnBackend isEqualToString:@"mpsgraph"] || [_cnnBackend isEqualToString:@"metal"]) {
#if defined(GPR_HAVE_SUPER_RES_METAL) && GPR_HAVE_SUPER_RES_METAL
            uint32_t inBayerW = _gprInput ? _codecInfo.width : _codecInfo.width;
            uint32_t inBayerH = _gprInput ? _codecInfo.height : _codecInfo.height;
            if (_noCodec && !_gprInput) { inBayerW = _info.width; inBayerH = _info.height; }
            uint32_t Wp = inBayerW / 2;
            uint32_t Hp = inBayerH / 2;
            uint32_t Wpp = (Wp + 7) & ~7u;
            uint32_t Hpp = (Hp + 7) & ~7u;
            SuperResMetalBackend be = [_cnnBackend isEqualToString:@"metal"]
                ? SuperResMetalBackendHybrid : SuperResMetalBackendMPSGraph;
            _cnnMetal = [[SuperResMetal alloc] initWithWeightsDir:_ckptPath
                                                            device:_device
                                                          inPlaneH:Hpp
                                                          inPlaneW:Wpp
                                                            backend:be];
            if (!_cnnMetal) { fprintf(stderr, "CNN(metal) init failed\n"); return nil; }
#else
            fprintf(stderr, "warning: --cnn-backend=%s requested but SuperResMetal not in this build; falling back to CoreML\n",
                    [_cnnBackend UTF8String]);
            _cnn = [[SuperResCNN alloc] initWithMLPackagePath:_ckptPath device:_device];
            if (!_cnn) { fprintf(stderr, "CNN init failed\n"); return nil; }
#endif
        } else {
            _cnn = [[SuperResCNN alloc] initWithMLPackagePath:_ckptPath device:_device];
            if (!_cnn) { fprintf(stderr, "CNN init failed\n"); return nil; }
        }
    }

    _writePending = [NSMutableDictionary dictionary];
    _nextWriteIdx = 0;
    _writeLock = [[NSLock alloc] init];

    fprintf(stderr, "  pipeline: %s%ux%u → ",
            _gprInput ? "GPR " : "",
            _info.width, _info.height);
    if (_gprInput)        fprintf(stderr, "decode→%ux%u → ", _codecInfo.width, _codecInfo.height);
    else if (!_noCodec)   fprintf(stderr, "codec→%ux%u → ", _codecInfo.width, _codecInfo.height);
    if (!_noCNN)          fprintf(stderr, "CNN→%ux%u → ", _info.width, _info.height);
    fprintf(stderr, "demosaic→ProRes(%ux%u@%dfps) [pipelined 4-deep]\n", demoW, demoH, _fps);
    return self;
}

// ============================================================================
// Pipelined stage implementations (shared by GPR + DNG runners)
// ============================================================================

// CNN stage: run the CNN super-res on job.bayer (decoded codec dims) and
// replace job.bayer with the upsampled native-dim Bayer.
- (int)runCNNStage:(FrameJob *)job {
    if (_noCNN) return 0;
    uint16_t *cnnBuf = malloc((size_t)_info.width * _info.height * 2);
    int crc;
    if (_cnnMetal) {
        crc = [_cnnMetal runOnBayer:job.bayer
                              width:job.bayerW height:job.bayerH
                           outBayer:cnnBuf
                           outWidth:_info.width
                          outHeight:_info.height
                         blackLevel:_info.blackLevel
                         whiteLevel:_info.whiteLevel];
    } else {
        crc = [_cnn runOnBayer:job.bayer
                         width:job.bayerW height:job.bayerH
                      outBayer:cnnBuf
                      outWidth:_info.width
                     outHeight:_info.height
                    blackLevel:_info.blackLevel
                    whiteLevel:_info.whiteLevel];
    }
    if (crc != 0) {
        fprintf(stderr, "CNN rc=%d (frame %d)\n", crc, job.idx);
        free(cnnBuf);
        return crc;
    }
    if (job.bayerOwned && job.bayer) free(job.bayer);
    job.bayer = cnnBuf;
    job.bayerOwned = YES;
    job.bayerW = _info.width;
    job.bayerH = _info.height;
    return 0;
}

// Demosaic + grab CVPixelBuffer. Encodes one MTLCommandBuffer; this method
// blocks until completion (so the next stage can safely append to ordered
// writer inbox with the bayer freed).
- (int)runDemosaicStage:(FrameJob *)job {
    CVPixelBufferRef pb = [_writer pixelBuffer];
    if (!pb) {
        fprintf(stderr, "no pixel buffer (frame %d)\n", job.idx);
        return -1;
    }
    // Retain across the inbox handoff (writer queue releases).
    CVPixelBufferRetain(pb);
    id<MTLCommandBuffer> cb = [_queue commandBuffer];
    [_demosaic encode:cb bayer:job.bayer width:job.bayerW height:job.bayerH outPixelBuffer:pb];
    [cb commit];
    [cb waitUntilCompleted];

    // Bayer is no longer needed.
    if (job.bayerOwned && job.bayer) { free(job.bayer); job.bayer = NULL; }
    job.bayer = NULL;
    job.bayerOwned = NO;
    job.pb = pb;
    return 0;
}

// Writer stage: insert into reorder buffer, drain in PTS order.
- (void)deliverToWriter:(FrameJob *)job {
    NSMutableArray<FrameJob *> *flushable = [NSMutableArray array];
    [_writeLock lock];
    _writePending[@(job.idx)] = job;
    while (1) {
        FrameJob *next = _writePending[@(_nextWriteIdx)];
        if (!next) break;
        [_writePending removeObjectForKey:@(_nextWriteIdx)];
        [flushable addObject:next];
        _nextWriteIdx++;
    }
    [_writeLock unlock];

    for (FrameJob *j in flushable) {
        double tw0 = now_ms();
        int wrc = [_writer appendPixelBuffer:j.pb frameIndex:j.idx];
        if (wrc != 0) fprintf(stderr, "append rc=%d (frame %d)\n", wrc, j.idx);
        CVPixelBufferRelease(j.pb);
        j.pb = NULL;
        double tw1 = now_ms();
        j.t_write = tw1 - tw0;

        if (self->_timing) {
            fprintf(stderr,
                "  frame %d  read=%.1fms decode=%.1fms cnn=%.1fms demosaic=%.1fms write=%.1fms total=%.1fms\n",
                j.idx, j.t_read, j.t_decode, j.t_cnn, j.t_demosaic, j.t_write,
                (now_ms() - j.t_submit));
        } else {
            fprintf(stderr, "  frame %d  total=%.1fms\n", j.idx, now_ms() - j.t_submit);
        }
    }
}

// ============================================================================
// GPR runner — pipelined.
// ============================================================================
- (int)runFramesGPR:(NSArray<NSString *> *)framePaths {
    double t_total_start = now_ms();
    NSUInteger N = framePaths.count;

    // Inbox capacities tuned for ~4 frames in flight total. Reader can stay
    // 2 ahead of CNN; CNN 2 ahead of demosaic; demosaic 4 ahead of writer.
    StageInbox *cnnInbox      = make_inbox("gpr2prores.cnn",      _noCNN ? 4 : 2);
    StageInbox *demosaicInbox = make_inbox("gpr2prores.demosaic", 2);
    StageInbox *writerInbox   = make_inbox("gpr2prores.writer",   4);

    // Reader is its own queue (concurrent reads if filesystem allows; serial
    // is fine since mmap+decode is fast). Keep serial so the GPRCodec decode
    // context is touched by one thread at a time (decode is stateless in C
    // but stays simple).
    dispatch_queue_t readerQueue = dispatch_queue_create("gpr2prores.reader", DISPATCH_QUEUE_SERIAL);
    dispatch_semaphore_t allDone = dispatch_semaphore_create(0);
    __block atomic_int writtenCount = 0;
    int totalN = (int)N;

    for (NSUInteger i = 0; i < N; i++) {
        NSString *path = framePaths[i];
        FrameJob *job = [[FrameJob alloc] init];
        job.idx = (int)i;
        job.path = path;
        job.t_submit = now_ms();

        // Reader stage: acquire a slot on cnnInbox first (backpressure: don't
        // get too far ahead of the CNN).
        dispatch_semaphore_wait(cnnInbox.slots, DISPATCH_TIME_FOREVER);
        dispatch_async(readerQueue, ^{
            double t0 = now_ms();
            GPRFileInfo gi = {0};
            NSData *encData = [GPRFileReader readEncodedFromPath:path info:&gi];
            if (encData && encData.length > 0) {
                volatile uint8_t v = ((const uint8_t *)encData.bytes)[0]; (void)v;
            }
            double t1 = now_ms();
            job.t_read = t1 - t0;
            if (!encData) {
                fprintf(stderr, "skip frame %d (read fail)\n", job.idx);
                dispatch_semaphore_signal(cnnInbox.slots);
                if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                    dispatch_semaphore_signal(allDone);
                }
                return;
            }

            // Decode in place on a per-job-allocated buffer.
            size_t dec_buf_sz = (size_t)gi.decWidth * gi.decHeight * 2;
            uint16_t *decBuf = malloc(dec_buf_sz);
            int dw = 0, dh = 0;
            int drc = [self->_codec decode:encData.bytes size:encData.length
                                  outBayer:decBuf
                                  outPitch:(size_t)gi.decWidth * 2
                                  outWidth:&dw outHeight:&dh];
            double t2 = now_ms();
            job.t_decode = t2 - t1;
            if (drc != 0) {
                fprintf(stderr, "decode rc=%d (frame %d)\n", drc, job.idx);
                free(decBuf);
                dispatch_semaphore_signal(cnnInbox.slots);
                if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                    dispatch_semaphore_signal(allDone);
                }
                return;
            }
            job.bayer = decBuf;
            job.bayerW = (uint32_t)dw;
            job.bayerH = (uint32_t)dh;
            job.bayerOwned = YES;

            // Hand to CNN queue. Reserve a demosaic slot before letting CNN
            // start, so CNN won't get more than `demosaicInbox.cap` ahead.
            dispatch_semaphore_wait(demosaicInbox.slots, DISPATCH_TIME_FOREVER);
            dispatch_async(cnnInbox.queue, ^{
                // Reader had reserved the cnn slot; release it now that we're
                // in the cnn stage (the slot tracks "frames awaiting CNN start").
                dispatch_semaphore_signal(cnnInbox.slots);

                double tc0 = now_ms();
                int rc = [self runCNNStage:job];
                double tc1 = now_ms();
                job.t_cnn = tc1 - tc0;
                if (rc != 0) {
                    dispatch_semaphore_signal(demosaicInbox.slots);
                    if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                        dispatch_semaphore_signal(allDone);
                    }
                    return;
                }

                // Hand to demosaic queue. Reserve a writer slot.
                dispatch_semaphore_wait(writerInbox.slots, DISPATCH_TIME_FOREVER);
                dispatch_async(demosaicInbox.queue, ^{
                    dispatch_semaphore_signal(demosaicInbox.slots);

                    double td0 = now_ms();
                    int rc2 = [self runDemosaicStage:job];
                    double td1 = now_ms();
                    job.t_demosaic = td1 - td0;
                    if (rc2 != 0) {
                        dispatch_semaphore_signal(writerInbox.slots);
                        if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                            dispatch_semaphore_signal(allDone);
                        }
                        return;
                    }

                    // Hand to writer queue.
                    dispatch_async(writerInbox.queue, ^{
                        [self deliverToWriter:job];
                        dispatch_semaphore_signal(writerInbox.slots);
                        if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                            dispatch_semaphore_signal(allDone);
                        }
                    });
                });
            });
        });
    }

    // Wait for all frames to write.
    dispatch_semaphore_wait(allDone, DISPATCH_TIME_FOREVER);

    [_writer finish];
    double t_total = now_ms() - t_total_start;
    fprintf(stderr, "DONE  total=%.1fs  output=%s  effective fps=%.2f\n",
            t_total / 1000.0, [_outPath UTF8String],
            framePaths.count / (t_total / 1000.0));
    return 0;
}

// ============================================================================
// DNG runner — pipelined. Same shape as GPR but reader does DNG read + encode
// + decode (when --no-codec is off). The GPRCodec's encoder is stateful so
// the encode step must remain serial within the reader queue (which it is).
// ============================================================================
- (int)runFramesDNG:(NSArray<NSString *> *)framePaths {
    double t_total_start = now_ms();
    NSUInteger N = framePaths.count;

    StageInbox *cnnInbox      = make_inbox("gpr2prores.cnn",      _noCNN ? 4 : 2);
    StageInbox *demosaicInbox = make_inbox("gpr2prores.demosaic", 2);
    StageInbox *writerInbox   = make_inbox("gpr2prores.writer",   4);
    dispatch_queue_t readerQueue = dispatch_queue_create("gpr2prores.reader", DISPATCH_QUEUE_SERIAL);
    dispatch_semaphore_t allDone = dispatch_semaphore_create(0);
    __block atomic_int writtenCount = 0;
    int totalN = (int)N;

    for (NSUInteger i = 0; i < N; i++) {
        NSString *path = framePaths[i];
        FrameJob *job = [[FrameJob alloc] init];
        job.idx = (int)i;
        job.path = path;
        job.t_submit = now_ms();

        dispatch_semaphore_wait(cnnInbox.slots, DISPATCH_TIME_FOREVER);
        dispatch_async(readerQueue, ^{
            double t0 = now_ms();
            DNGInfo info_local;
            uint16_t *bayer = [DNGReader readBayerFromPath:path info:&info_local];
            double t1 = now_ms();
            job.t_read = t1 - t0;
            if (!bayer) {
                fprintf(stderr, "skip %s (read fail)\n", [path UTF8String]);
                dispatch_semaphore_signal(cnnInbox.slots);
                if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                    dispatch_semaphore_signal(allDone);
                }
                return;
            }

            uint16_t *currentBayer = bayer;
            BOOL ownsCurrent = YES;
            uint32_t currentW = info_local.width;
            uint32_t currentH = info_local.height;

            if (!self->_noCodec) {
                uint8_t *vc5 = NULL; size_t vc5_size = 0;
                int erc = [self->_codec encodeRawBayer:currentBayer
                                                bytes:(size_t)currentW * currentH * 2
                                              vc5Out:&vc5
                                             vc5Size:&vc5_size];
                if (erc != 0) {
                    fprintf(stderr, "encode rc=%d (frame %d)\n", erc, job.idx);
                    free(bayer);
                    dispatch_semaphore_signal(cnnInbox.slots);
                    if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                        dispatch_semaphore_signal(allDone);
                    }
                    return;
                }
                uint16_t *codecBuf = malloc((size_t)self->_codecInfo.width * self->_codecInfo.height * 2);
                int dw = 0, dh = 0;
                int drc = [self->_codec decode:vc5 size:vc5_size
                                       outBayer:codecBuf
                                      outPitch:(size_t)self->_codecInfo.width * 2
                                       outWidth:&dw outHeight:&dh];
                if (drc != 0) {
                    fprintf(stderr, "decode rc=%d (frame %d)\n", drc, job.idx);
                    free(codecBuf);
                    free(bayer);
                    dispatch_semaphore_signal(cnnInbox.slots);
                    if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                        dispatch_semaphore_signal(allDone);
                    }
                    return;
                }
                // Replace currentBayer (free original)
                if (ownsCurrent) free(currentBayer);
                currentBayer = codecBuf;
                currentW = (uint32_t)dw;
                currentH = (uint32_t)dh;
                ownsCurrent = YES;
            }
            double t2 = now_ms();
            job.t_decode = t2 - t1;

            job.bayer = currentBayer;
            job.bayerW = currentW;
            job.bayerH = currentH;
            job.bayerOwned = ownsCurrent;

            dispatch_semaphore_wait(demosaicInbox.slots, DISPATCH_TIME_FOREVER);
            dispatch_async(cnnInbox.queue, ^{
                dispatch_semaphore_signal(cnnInbox.slots);
                double tc0 = now_ms();
                int rc = [self runCNNStage:job];
                double tc1 = now_ms();
                job.t_cnn = tc1 - tc0;
                if (rc != 0) {
                    dispatch_semaphore_signal(demosaicInbox.slots);
                    if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                        dispatch_semaphore_signal(allDone);
                    }
                    return;
                }

                dispatch_semaphore_wait(writerInbox.slots, DISPATCH_TIME_FOREVER);
                dispatch_async(demosaicInbox.queue, ^{
                    dispatch_semaphore_signal(demosaicInbox.slots);
                    double td0 = now_ms();
                    int rc2 = [self runDemosaicStage:job];
                    double td1 = now_ms();
                    job.t_demosaic = td1 - td0;
                    if (rc2 != 0) {
                        dispatch_semaphore_signal(writerInbox.slots);
                        if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                            dispatch_semaphore_signal(allDone);
                        }
                        return;
                    }

                    dispatch_async(writerInbox.queue, ^{
                        [self deliverToWriter:job];
                        dispatch_semaphore_signal(writerInbox.slots);
                        if (atomic_fetch_add(&writtenCount, 1) + 1 == totalN) {
                            dispatch_semaphore_signal(allDone);
                        }
                    });
                });
            });
        });
    }

    dispatch_semaphore_wait(allDone, DISPATCH_TIME_FOREVER);

    [_writer finish];
    double t_total = now_ms() - t_total_start;
    fprintf(stderr, "DONE  total=%.1fs  output=%s  effective fps=%.2f\n",
            t_total / 1000.0, [_outPath UTF8String],
            framePaths.count / (t_total / 1000.0));
    return 0;
}

- (int)runFrames:(NSArray<NSString *> *)framePaths {
    return _gprInput ? [self runFramesGPR:framePaths]
                     : [self runFramesDNG:framePaths];
}

@end
