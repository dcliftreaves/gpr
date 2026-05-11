/*! @file fast_decode.c
 *
 *  @brief Ultra-fast VC5 decoder: pre-index + parallel band decode + wavelet reconstruct.
 *
 *  Replaces the serial tag-by-tag decoder in decoder.c with:
 *  1. Pre-index: single pass over VC5 tags → band offset table (< 1ms)
 *  2. Parallel decode: N threads decode independent ANS bands simultaneously
 *  3. Direct lowpass decode: byte-swap 16-bit big-endian coefficients (no bitstream)
 *  4. Wavelet reconstruction: intermediate levels + final output (parallel per channel)
 *
 *  Entry point: DecodeFastImage() — drop-in replacement for DecodeImage() in vc5_decoder_process.
 *
 *  (C) Copyright 2018 GoPro Inc (http://gopro.com/).
 *  Licensed under Apache-2.0 or MIT at your option.
 */

#include "headers.h"
#include "ans_joint.h"
#ifndef _WIN32
#include <pthread.h>
#endif
#include <string.h>
#include <stdlib.h>

/* ================================================================
   Pre-indexer: single fast pass over VC5 tag stream
   ================================================================ */

#define FAST_MAX_BANDS 48  /* 4 channels × 12 bands max */

typedef struct {
    int channel;
    int subband;
    int coding_method;    /* 0=VLC, 1/2=ANS, 3/4=ANS interleaved */
    int quantization;
    int lowpass_precision;
    size_t data_offset;   /* Offset from start of VC5 blob */
    size_t data_size;     /* Codeblock size in bytes */
} FAST_BAND_INFO;

typedef struct {
    int image_width;
    int image_height;
    int channel_count;
    int bits_per_component;
    int max_bits_per_component;
    int prescale_shift;   /* Raw tag 109 value for unpacking */
    int band_count;
    FAST_BAND_INFO bands[FAST_MAX_BANDS];
} FAST_INDEX;

/* StartMarker: "VC-5" = 0x56432D35 */
static const uint32_t VC5_START_MARKER = ((0x56 << 24) | (0x43 << 16) | (0x2D << 8) | 0x35);

/*! Scan the VC5 tag stream and build an index of all band codeblocks.
    Also extracts image metadata needed to set up the decoder. */
static int fast_preindex(const uint8_t *buf, size_t size, FAST_INDEX *idx)
{
    memset(idx, 0, sizeof(*idx));
    idx->channel_count = 4; /* Bayer default */
    idx->bits_per_component = 14; /* Default */

    size_t pos = 0;
    int cur_channel = 0, cur_subband = 0, cur_quant = 1, cur_coding = 0;
    int cur_lowpass_prec = 16;

    /* Skip start marker */
    if (size >= 4) {
        uint32_t marker = ((uint32_t)buf[0] << 24) | ((uint32_t)buf[1] << 16) |
                          ((uint32_t)buf[2] << 8) | buf[3];
        if (marker == VC5_START_MARKER)
            pos = 4;
    }

    while (pos + 4 <= size) {
        uint32_t word = ((uint32_t)buf[pos] << 24) | ((uint32_t)buf[pos+1] << 16) |
                        ((uint32_t)buf[pos+2] << 8) | buf[pos+3];
        pos += 4;

        int16_t raw_tag = (int16_t)(word >> 16);
        int16_t value = (int16_t)(word & 0xFFFF);

        /* Handle optional (negative) tags */
        int tag = raw_tag;
        if (tag < 0) tag = -tag;

        /* VC5 tag classification (after removing optional bit):
           Bit 14 (0x4000) = small chunk (payload follows, e.g., UUID)
           Bit 13 (0x2000) = large chunk section header (channel/header section - parse inline)
           Both (0x6000) = codeblock (band data)
           Neither = regular tag-value pair */

        /* Codeblock: both chunk bits set (0x6000) */
        if ((tag & 0x6000) == 0x6000) {
            /* Compute 24-bit size: (tag & 0xFF) << 16 | value, in 32-bit words */
            size_t chunk_words = ((size_t)(tag & 0xFF) << 16) | ((size_t)(uint16_t)value);
            size_t chunk_bytes = chunk_words * 4;

            if (idx->band_count < FAST_MAX_BANDS) {
                FAST_BAND_INFO *b = &idx->bands[idx->band_count];
                b->channel = cur_channel;
                b->subband = cur_subband;
                b->coding_method = cur_coding;
                b->quantization = cur_quant;
                b->lowpass_precision = cur_lowpass_prec;
                b->data_offset = pos;
                b->data_size = chunk_bytes;
                idx->band_count++;
            }
            cur_coding = 0; /* Reset for next band */
            pos += chunk_bytes;
            continue;
        }

        /* Small chunk (bit 14 only, 0x4000): UUID, inverse transform, etc.
           These have inline payload data that is NOT tags — must skip. */
        if ((tag & 0x4000) && !(tag & 0x2000)) {
            size_t chunk_bytes = (size_t)(uint16_t)value * 4;
            pos += chunk_bytes;
            continue;
        }

        /* Large non-codeblock sections (bit 13 only, 0x2000): channel/header sections.
           These are containers whose content is more tags and codeblocks.
           Do NOT skip — just continue parsing the inline content. */

        /* Parse metadata tags (non-chunk tag-value pairs and section headers) */
        switch (tag) {
            case 20: idx->image_width = value; break;          /* ImageWidth */
            case 21: idx->image_height = value; break;         /* ImageHeight */
            case 12: idx->channel_count = value; break;        /* ChannelCount */
            case 62: cur_channel = value; break;               /* ChannelNumber */
            case 48: cur_subband = value; break;               /* SubbandNumber */
            case 53: cur_quant = value; break;                 /* Quantization */
            case 35: cur_lowpass_prec = value; break;          /* LowpassPrecision */
            case 101: idx->bits_per_component = value; break;  /* BitsPerComponent */
            case 102: idx->max_bits_per_component = value; break; /* MaxBitsPerComponent */
            case 109: idx->prescale_shift = value; break;      /* PrescaleShift */
            case 200: cur_coding = value; break;               /* BandCodingMethod */
            default: break;
        }
    }

    return (idx->band_count > 0) ? 0 : -1;
}

/* ================================================================
   Lowpass band decoder: direct byte-swap from raw buffer
   ================================================================ */

/*! Decode the lowpass band (subband 0) directly from codeblock data.
    Lowpass coefficients are stored as 16-bit big-endian values. */
static void fast_decode_lowpass(const uint8_t *data, size_t data_size,
                                PIXEL *output, int width, int height, int pitch_pixels,
                                int precision)
{
    const uint8_t *src = data;

    if (precision == 16) {
        for (int row = 0; row < height; row++) {
            PIXEL *row_ptr = output + row * pitch_pixels;
            for (int col = 0; col < width; col++) {
                /* Big-endian 16-bit signed → int32_t PIXEL */
                row_ptr[col] = (COEFFICIENT)((int16_t)((uint16_t)(src[0] << 8) | src[1]));
                src += 2;
            }
        }
    } else {
        /* Generic: read 'precision' bits per coefficient
           For non-16-bit, fall back to bit-by-bit (rare) */
        for (int row = 0; row < height; row++) {
            PIXEL *row_ptr = output + row * pitch_pixels;
            for (int col = 0; col < width; col++) {
                /* Assume byte-aligned for simplicity */
                int val = 0;
                int bits_left = precision;
                while (bits_left >= 8) {
                    val = (val << 8) | *src++;
                    bits_left -= 8;
                }
                if (bits_left > 0) {
                    val = (val << bits_left) | (*src >> (8 - bits_left));
                }
                row_ptr[col] = (COEFFICIENT)val;
            }
        }
    }
}

/* ================================================================
   Parallel ANS band decode
   ================================================================ */

typedef struct {
    const uint8_t *vc5_base;     /* Base of VC5 blob */
    FAST_BAND_INFO *band;        /* Band to decode */
    PIXEL *output;               /* Pre-allocated wavelet band buffer */
    int width;                   /* Band width */
    int height;                  /* Band height */
    int pitch;                   /* Output pitch in bytes */
    int error;                   /* 0=ok, -1=fatal */
} FAST_ANS_ARG;

static void *fast_ans_decode_thread(void *arg)
{
    FAST_ANS_ARG *a = (FAST_ANS_ARG *)arg;
    FAST_BAND_INFO *b = a->band;
    a->error = 0;

    const uint8_t *cblock = a->vc5_base + b->data_offset;
    size_t cblock_size = b->data_size;

    if (cblock_size < 4) { a->error = -1; return NULL; }

    /* First 4 bytes of codeblock = ANS blob size (big-endian uint32) */
    uint32_t ans_size = ((uint32_t)cblock[0] << 24) | ((uint32_t)cblock[1] << 16) |
                        ((uint32_t)cblock[2] << 8) | cblock[3];
    const uint8_t *ans_blob = cblock + 4;

    if (4 + ans_size > cblock_size) { a->error = -1; return NULL; }

    int rc;
    if (b->coding_method >= 3)
        rc = jans_decode_band_x4(ans_blob, ans_size,
                                  (int32_t *)a->output,
                                  a->width, a->height, a->pitch);
    else
        rc = jans_decode_band(ans_blob, ans_size,
                               (int32_t *)a->output,
                               a->width, a->height, a->pitch);

    if (rc != 0) a->error = -1;
    return NULL;
}

/* ================================================================
   VLC band decode (serial, using existing codebook)
   ================================================================ */

/* Use the standard decoder codebook for VLC fallback */
#include "codebooks.h"

static int fast_decode_vlc_band(const uint8_t *vc5_buf, FAST_BAND_INFO *band,
                                PIXEL *output, int width, int height, int pitch)
{
    /* Set up a memory stream at the band's codeblock offset */
    STREAM stream;
    BITSTREAM bitstream;

    /* Create a memory stream starting at the codeblock data */
    const uint8_t *cblock_start = vc5_buf + band->data_offset;
    size_t cblock_size = band->data_size;

    memset(&stream, 0, sizeof(stream));
    stream.type = STREAM_TYPE_MEMORY;
    stream.location.memory.buffer = (void *)cblock_start;
    stream.location.memory.size = cblock_size;
    stream.byte_count = 0;

    InitBitstream(&bitstream);
    AttachBitstream(&bitstream, &stream);

    CODEBOOK *codebook = (CODEBOOK *)decoder_codeset_17.codebook;
    if (!codebook) return -1;

    CODEC_ERROR err = DecodeBandRuns(&bitstream, codebook, output,
                                     (DIMENSION)width, (DIMENSION)height, (DIMENSION)pitch);

    ReleaseBitstream(&bitstream);
    return (err == CODEC_ERROR_OKAY) ? 0 : -1;
}

/* ================================================================
   Wavelet tree construction and intermediate reconstruction
   ================================================================ */

/* Thread argument for full per-channel wavelet reconstruction.
   Each thread handles ALL 3 levels of inverse transform for one channel:
   wavelet[2] → wavelet[1].LL → wavelet[0].LL → output */
typedef struct {
    gpr_allocator *allocator;
    WAVELET *wavelets[MAX_WAVELET_COUNT]; /* All wavelet levels for this channel */
    PRESCALE prescale_table[MAX_WAVELET_COUNT];
    COMPONENT_VALUE *output_data;
    DIMENSION output_width;
    DIMENSION output_height;
    size_t output_pitch;
    CODEC_ERROR error;
} FAST_CHANNEL_RECON_ARG;

static void *fast_channel_recon_thread(void *arg)
{
    FAST_CHANNEL_RECON_ARG *a = (FAST_CHANNEL_RECON_ARG *)arg;
    a->error = CODEC_ERROR_OKAY;

    /* Level 2 → Level 1 lowpass */
    if (BandsAllValid(a->wavelets[2])) {
        TransformInverseSpatialQuantLowpass(a->allocator,
                                            a->wavelets[2], a->wavelets[1],
                                            a->prescale_table[2]);
        UpdateWaveletValidBandMask(a->wavelets[1], 0);
    }

    /* Level 1 → Level 0 lowpass */
    if (BandsAllValid(a->wavelets[1])) {
        TransformInverseSpatialQuantLowpass(a->allocator,
                                            a->wavelets[1], a->wavelets[0],
                                            a->prescale_table[1]);
        UpdateWaveletValidBandMask(a->wavelets[0], 0);
    }

    /* Level 0 → final output */
    if (BandsAllValid(a->wavelets[0])) {
        a->error = TransformInverseSpatialQuantArray(a->allocator,
                                                      a->wavelets[0],
                                                      a->output_data,
                                                      a->output_width,
                                                      a->output_height,
                                                      a->output_pitch,
                                                      a->prescale_table[0]);
    }

    return NULL;
}

/* ================================================================
   Parallel image packing (row-striped)
   ================================================================ */

typedef struct {
    const UNPACKED_IMAGE *image;
    PACKED_IMAGE *packed;
    const DECODER_PARAMETERS *params;
    int row_start;    /* First row (in Bayer half-rows) */
    int row_end;      /* Last row (exclusive) */
} FAST_PACK_ARG;

static void *fast_pack_thread(void *arg)
{
    FAST_PACK_ARG *a = (FAST_PACK_ARG *)arg;
    const UNPACKED_IMAGE *image = a->image;
    PACKED_IMAGE *packed = a->packed;

    DIMENSION width = packed->width / 2;   /* Bayer pattern units */
    size_t output_pitch = packed->pitch * 2;
    PIXEL_FORMAT output_format = packed->format;
    int output_bit_depth = 14;

    /* Determine output bit depth from format */
    switch (output_format) {
        case PIXEL_FORMAT_RAW_RGGB_12: case PIXEL_FORMAT_RAW_GBRG_12: output_bit_depth = 12; break;
        case PIXEL_FORMAT_RAW_RGGB_14: case PIXEL_FORMAT_RAW_GBRG_14: output_bit_depth = 14; break;
        case PIXEL_FORMAT_RAW_RGGB_16: case PIXEL_FORMAT_RAW_GBRG_16: output_bit_depth = 16; break;
        default: break;
    }

    int rggb_order = (output_format == PIXEL_FORMAT_RAW_RGGB_12 ||
                      output_format == PIXEL_FORMAT_RAW_RGGB_14 ||
                      output_format == PIXEL_FORMAT_RAW_RGGB_16) ? 1 : 0;

    int log_bits = image->component_array_list[0].bits_per_component;
    if (log_bits <= 0) log_bits = 12;
    if (log_bits > 16) log_bits = 16;

    /* Use appropriate log curve table */
    uint16_t *log_table;
    int log_max;
    if (log_bits <= 12) { log_table = DecoderLogCurve12; log_max = (1 << 12) - 1; }
    else if (log_bits <= 14) { log_table = DecoderLogCurve14; log_max = (1 << 14) - 1; }
    else { log_table = DecoderLogCurve16; log_max = (1 << 16) - 1; }

    const int32_t midpoint = 1 << (log_bits - 1);
    const int shift = 16 - output_bit_depth;
    size_t output_half_pitch = output_pitch / 2;
    int bypass = vc5_logcurve_bypass();

    for (int row = a->row_start; row < a->row_end; row++)
    {
        COMPONENT_VALUE *GS_row = (COMPONENT_VALUE *)((uintptr_t)image->component_array_list[0].data + row * image->component_array_list[0].pitch);
        COMPONENT_VALUE *RG_row = (COMPONENT_VALUE *)((uintptr_t)image->component_array_list[1].data + row * image->component_array_list[1].pitch);
        COMPONENT_VALUE *BG_row = (COMPONENT_VALUE *)((uintptr_t)image->component_array_list[2].data + row * image->component_array_list[2].pitch);
        COMPONENT_VALUE *GD_row = (COMPONENT_VALUE *)((uintptr_t)image->component_array_list[3].data + row * image->component_array_list[3].pitch);

        uint8_t *output_row_ptr = (uint8_t *)packed->buffer + row * output_pitch;
        uint16_t *out_row1 = (uint16_t *)output_row_ptr;
        uint16_t *out_row2 = (uint16_t *)(output_row_ptr + output_half_pitch);

        for (int col = 0; col < (int)width; col++)
        {
            int32_t GS = GS_row[col], RG = RG_row[col], BG = BG_row[col], GD = GD_row[col];

            /* Clamp to valid range */
            if (GS < 0) GS = 0; else if (GS > log_max) GS = log_max;
            if (RG < 0) RG = 0; else if (RG > log_max) RG = log_max;
            if (BG < 0) BG = 0; else if (BG > log_max) BG = log_max;
            if (GD < 0) GD = 0; else if (GD > log_max) GD = log_max;

            GD -= midpoint; RG -= midpoint; BG -= midpoint;

            int32_t R  = (RG << 1) + GS;
            int32_t B  = (BG << 1) + GS;
            int32_t G1 = GS + GD;
            int32_t G2 = GS - GD;

            if (R < 0) R = 0; else if (R > log_max) R = log_max;
            if (G1 < 0) G1 = 0; else if (G1 > log_max) G1 = log_max;
            if (G2 < 0) G2 = 0; else if (G2 > log_max) G2 = log_max;
            if (B < 0) B = 0; else if (B > log_max) B = log_max;

            if (!bypass) {
                R  = log_table[R]  >> shift;
                G1 = log_table[G1] >> shift;
                G2 = log_table[G2] >> shift;
                B  = log_table[B]  >> shift;
            }

            if (rggb_order) {
                out_row1[2*col]   = (uint16_t)R;
                out_row1[2*col+1] = (uint16_t)G1;
                out_row2[2*col]   = (uint16_t)G2;
                out_row2[2*col+1] = (uint16_t)B;
            } else {
                out_row1[2*col]   = (uint16_t)G1;
                out_row1[2*col+1] = (uint16_t)B;
                out_row2[2*col]   = (uint16_t)R;
                out_row2[2*col+1] = (uint16_t)G2;
            }
        }
    }
    return NULL;
}

/* ================================================================
   Main entry: DecodeFastImage — drop-in replacement for DecodeImage
   ================================================================ */

CODEC_ERROR DecodeFastImage(const uint8_t *vc5_buf, size_t vc5_size,
                            IMAGE *packed_image, RGB_IMAGE *rgb_image,
                            DECODER_PARAMETERS *parameters)
{
    CODEC_ERROR error = CODEC_ERROR_OKAY;

    /* Initialize LUTs (same as DecodeImage) */
    SetupDecoderLogCurve();
    InitUncompandTable();

    /* ---- Step 1: Pre-index the VC5 bitstream ---- */
    FAST_INDEX idx;
    if (fast_preindex(vc5_buf, vc5_size, &idx) != 0)
        return CODEC_ERROR_MISSING_START_MARKER;

    int channel_count = idx.channel_count;
    int channel_width = idx.image_width / 2;   /* Bayer: each channel is half the image */
    int channel_height = idx.image_height / 2;

    /* Determine bits per component */
    int bits_per_component = idx.max_bits_per_component;
    if (bits_per_component == 0)
        bits_per_component = idx.bits_per_component;
    if (bits_per_component == 0)
        bits_per_component = 14; /* Default */

    /* Unpack prescale table from tag 109 value */
    PRESCALE prescale_table[MAX_WAVELET_COUNT];
    for (int i = 0; i < MAX_WAVELET_COUNT; i++) {
        prescale_table[i] = (idx.prescale_shift >> (14 - i * 2)) & 0x03;
    }


    /* ---- Step 2: Create wavelets for all channels ---- */
    gpr_allocator *allocator = &parameters->allocator;
    WAVELET *wavelets[MAX_CHANNEL_COUNT][MAX_WAVELET_COUNT];
    memset(wavelets, 0, sizeof(wavelets));

    for (int ch = 0; ch < channel_count; ch++) {
        int w = channel_width;
        int h = channel_height;
        for (int level = 0; level < MAX_WAVELET_COUNT; level++) {
            /* Pad to even */
            if (w % 2 != 0) w++;
            if (h % 2 != 0) h++;
            w /= 2;
            h /= 2;

            wavelets[ch][level] = CreateWavelet(allocator, w, h);
            if (!wavelets[ch][level]) {
                error = CODEC_ERROR_OUTOFMEMORY;
                goto cleanup;
            }
        }
    }


    /* ---- Step 3: Map pre-indexed bands to wavelet tree positions ---- */
    /* Subband mapping: same as SubbandWaveletIndex/SubbandBandIndex */
    static const int subband_wavelet[] = {2, 2, 2, 2, 1, 1, 1, 0, 0, 0};
    static const int subband_band[]    = {0, 1, 2, 3, 1, 2, 3, 1, 2, 3};

    /* Count of ANS bands for parallel dispatch */
    int ans_band_count = 0;
    FAST_ANS_ARG ans_args[FAST_MAX_BANDS];

    for (int i = 0; i < idx.band_count; i++) {
        FAST_BAND_INFO *b = &idx.bands[i];
        int ch = b->channel;
        int sub = b->subband;

        if (ch < 0 || ch >= channel_count || sub < 0 || sub >= MAX_SUBBAND_COUNT)
            continue;

        int wlevel = subband_wavelet[sub];
        int wband = subband_band[sub];
        WAVELET *wav = wavelets[ch][wlevel];

        if (sub == 0) {
            /* ---- Lowpass band: direct byte-swap decode ---- */
            fast_decode_lowpass(vc5_buf + b->data_offset, b->data_size,
                                wav->data[0], wav->width, wav->height,
                                wav->pitch / sizeof(PIXEL),
                                b->lowpass_precision);
            UpdateWaveletValidBandMask(wav, 0);
            wav->quant[0] = 1; /* Lowpass has no quantization */
        }
        else if (b->coding_method >= 1) {
            /* ---- ANS band: queue for parallel decode ---- */
            FAST_ANS_ARG *a = &ans_args[ans_band_count];
            a->vc5_base = vc5_buf;
            a->band = b;
            a->output = wav->data[wband];
            a->width = wav->width;
            a->height = wav->height;
            a->pitch = wav->pitch;
            a->error = 0;
            ans_band_count++;

            wav->quant[wband] = b->quantization;
            /* ANS modes 2/4: negate quant to skip uncompanding in dequantizer */
            if (b->coding_method == 2 || b->coding_method == 4) {
                wav->quant[wband] = -wav->quant[wband];
            }
            UpdateWaveletValidBandMask(wav, wband);
        }
        else {
            /* ---- VLC band: decode serially ---- */
            int rc = fast_decode_vlc_band(vc5_buf, b,
                                           wav->data[wband],
                                           wav->width, wav->height,
                                           wav->pitch);
            if (rc != 0) {
                error = CODEC_ERROR_DECODING_SUBBAND;
                goto cleanup;
            }
            wav->quant[wband] = b->quantization;
            UpdateWaveletValidBandMask(wav, wband);
        }
    }

    /* ---- Step 4: Parallel ANS decode ---- */
#ifndef _WIN32
    {
        pthread_t threads[FAST_MAX_BANDS];
        int thread_count = 0;

        for (int i = 0; i < ans_band_count; i++) {
            if (pthread_create(&threads[thread_count], NULL,
                               fast_ans_decode_thread, &ans_args[i]) == 0) {
                thread_count++;
            } else {
                /* Thread creation failed: decode inline */
                fast_ans_decode_thread(&ans_args[i]);
            }
        }

        for (int i = 0; i < thread_count; i++) {
            pthread_join(threads[i], NULL);
        }
    }
#else
    for (int i = 0; i < ans_band_count; i++) {
        fast_ans_decode_thread(&ans_args[i]);
    }
#endif

    /* Check for ANS decode errors */
    for (int i = 0; i < ans_band_count; i++) {
        if (ans_args[i].error != 0) {
            error = CODEC_ERROR_DECODING_SUBBAND;
            goto cleanup;
        }
    }

    /* ---- Step 5+6: Full wavelet reconstruction (all levels) in parallel per channel ---- */
    {
        UNPACKED_IMAGE unpacked_image;
        InitUnpackedImage(&unpacked_image);

        /* Allocate component arrays */
        size_t comp_size = channel_count * sizeof(COMPONENT_ARRAY);
        unpacked_image.component_array_list = allocator->Alloc(comp_size);
        if (!unpacked_image.component_array_list) {
            error = CODEC_ERROR_OUTOFMEMORY;
            goto cleanup;
        }
        unpacked_image.component_count = channel_count;
        memset(unpacked_image.component_array_list, 0, comp_size);

        for (int ch = 0; ch < channel_count; ch++) {
            error = AllocateComponentArray(allocator,
                                            &unpacked_image.component_array_list[ch],
                                            channel_width, channel_height,
                                            bits_per_component);
            if (error != CODEC_ERROR_OKAY) goto cleanup;
        }

        /* Run ALL wavelet reconstruction levels in parallel (one thread per channel).
           Each thread does: level 2→1, level 1→0, level 0→output */
#ifndef _WIN32
        {
            pthread_t threads[MAX_CHANNEL_COUNT];
            FAST_CHANNEL_RECON_ARG recon_args[MAX_CHANNEL_COUNT];
            int thread_created[MAX_CHANNEL_COUNT];

            for (int ch = 0; ch < channel_count; ch++) {
                recon_args[ch].allocator = allocator;
                for (int lvl = 0; lvl < MAX_WAVELET_COUNT; lvl++) {
                    recon_args[ch].wavelets[lvl] = wavelets[ch][lvl];
                    recon_args[ch].prescale_table[lvl] = prescale_table[lvl];
                }
                recon_args[ch].output_data  = unpacked_image.component_array_list[ch].data;
                recon_args[ch].output_width = channel_width;
                recon_args[ch].output_height = channel_height;
                recon_args[ch].output_pitch = unpacked_image.component_array_list[ch].pitch;
                recon_args[ch].error        = CODEC_ERROR_OKAY;

                thread_created[ch] = (pthread_create(&threads[ch], NULL,
                                                      fast_channel_recon_thread,
                                                      &recon_args[ch]) == 0);
                if (!thread_created[ch]) {
                    fast_channel_recon_thread(&recon_args[ch]);
                }
            }

            for (int ch = 0; ch < channel_count; ch++) {
                if (thread_created[ch])
                    pthread_join(threads[ch], NULL);
                if (recon_args[ch].error != CODEC_ERROR_OKAY)
                    error = recon_args[ch].error;
            }
        }
#else
        for (int ch = 0; ch < channel_count; ch++) {
            FAST_CHANNEL_RECON_ARG recon_arg;
            recon_arg.allocator = allocator;
            for (int lvl = 0; lvl < MAX_WAVELET_COUNT; lvl++) {
                recon_arg.wavelets[lvl] = wavelets[ch][lvl];
                recon_arg.prescale_table[lvl] = prescale_table[lvl];
            }
            recon_arg.output_data  = unpacked_image.component_array_list[ch].data;
            recon_arg.output_width = channel_width;
            recon_arg.output_height = channel_height;
            recon_arg.output_pitch = unpacked_image.component_array_list[ch].pitch;
            recon_arg.error        = CODEC_ERROR_OKAY;
            fast_channel_recon_thread(&recon_arg);
            if (recon_arg.error != CODEC_ERROR_OKAY)
                error = recon_arg.error;
        }
#endif

        if (error != CODEC_ERROR_OKAY) {
            ReleaseComponentArrays(allocator, &unpacked_image, channel_count);
            goto cleanup;
        }


        /* ---- Step 7: Apply inverse variance-stabilizing transform if needed ---- */
        if (parameters->variance_stabilize && parameters->noise_scale > 0.0)
        {
            /* Defined in decoder.c as static — we inline the same logic */
            for (int ch = 0; ch < channel_count; ch++)
            {
                COMPONENT_VALUE *data = unpacked_image.component_array_list[ch].data;
                DIMENSION w = unpacked_image.component_array_list[ch].width;
                DIMENSION h = unpacked_image.component_array_list[ch].height;
                size_t pitch = unpacked_image.component_array_list[ch].pitch;
                double alpha = parameters->noise_scale;
                double sigma_sq = parameters->noise_offset;

                if (alpha > 0.0) {
                    double half_alpha = alpha / 2.0;
                    double offset = 3.0 / 8.0 * alpha * alpha + sigma_sq;
                    int pitch_elems = (int)(pitch / sizeof(COMPONENT_VALUE));
                    for (int row = 0; row < (int)h; row++) {
                        COMPONENT_VALUE *row_ptr = data + row * pitch_elems;
                        for (int col = 0; col < (int)w; col++) {
                            double d = (double)row_ptr[col];
                            double val = half_alpha * d;
                            val = val * val;
                            val = (val - offset) / alpha;
                            row_ptr[col] = (COMPONENT_VALUE)(val + 0.5);
                        }
                    }
                }
            }
        }

        /* ---- Step 8: Pack output image ---- */
        switch (parameters->rgb_resolution) {
            case GPR_RGB_RESOLUTION_NONE:
            {
                /* Determine output format from parameters */
                DIMENSION packed_width = idx.image_width;
                DIMENSION packed_height = idx.image_height;
                PIXEL_FORMAT packed_format = parameters->output.format;

                AllocImage(allocator, packed_image, packed_width, packed_height, packed_format);

                /* Parallel image packing: split rows across threads */
                {
                    int half_height = packed_height / 2;
                    int num_pack_threads = 4;
                    if (num_pack_threads > half_height) num_pack_threads = half_height;

#ifndef _WIN32
                    {
                        pthread_t pack_threads[8];
                        FAST_PACK_ARG pack_args[8];
                        int pack_created[8];
                        int rows_per = half_height / num_pack_threads;

                        for (int t = 0; t < num_pack_threads; t++) {
                            pack_args[t].image = &unpacked_image;
                            pack_args[t].packed = packed_image;
                            pack_args[t].params = parameters;
                            pack_args[t].row_start = t * rows_per;
                            pack_args[t].row_end = (t == num_pack_threads - 1) ? half_height : (t + 1) * rows_per;

                            pack_created[t] = (pthread_create(&pack_threads[t], NULL,
                                                               fast_pack_thread, &pack_args[t]) == 0);
                            if (!pack_created[t])
                                fast_pack_thread(&pack_args[t]);
                        }

                        for (int t = 0; t < num_pack_threads; t++) {
                            if (pack_created[t])
                                pthread_join(pack_threads[t], NULL);
                        }
                    }
#else
                    ImageRepackingProcess(&unpacked_image, packed_image, parameters);
#endif
                }
                break;
            }

            case GPR_RGB_RESOLUTION_HALF:
            {
                WaveletToRGB(*allocator,
                             (PIXEL*)unpacked_image.component_array_list[0].data,
                             (PIXEL*)unpacked_image.component_array_list[1].data,
                             (PIXEL*)unpacked_image.component_array_list[2].data,
                             unpacked_image.component_array_list[2].width,
                             unpacked_image.component_array_list[2].height,
                             unpacked_image.component_array_list[2].pitch / sizeof(COMPONENT_VALUE),
                             rgb_image, bits_per_component,
                             parameters->rgb_bits, &parameters->rgb_gain);
                break;
            }

            case GPR_RGB_RESOLUTION_QUARTER:
            {
                WaveletToRGB(*allocator,
                             wavelets[0][0]->data[0], wavelets[1][0]->data[0],
                             wavelets[2][0]->data[0],
                             wavelets[2][0]->width, wavelets[2][0]->height,
                             wavelets[2][0]->width,
                             rgb_image, bits_per_component,
                             parameters->rgb_bits, &parameters->rgb_gain);
                break;
            }

            case GPR_RGB_RESOLUTION_EIGHTH:
            {
                WaveletToRGB(*allocator,
                             wavelets[0][1]->data[0], wavelets[1][1]->data[0],
                             wavelets[2][1]->data[0],
                             wavelets[2][1]->width, wavelets[2][1]->height,
                             wavelets[2][1]->width,
                             rgb_image, bits_per_component,
                             parameters->rgb_bits, &parameters->rgb_gain);
                break;
            }

            case GPR_RGB_RESOLUTION_SIXTEENTH:
            {
                WaveletToRGB(*allocator,
                             wavelets[0][2]->data[0], wavelets[1][2]->data[0],
                             wavelets[2][2]->data[0],
                             wavelets[2][2]->width, wavelets[2][2]->height,
                             wavelets[2][2]->width,
                             rgb_image, bits_per_component,
                             parameters->rgb_bits, &parameters->rgb_gain);
                break;
            }

            default:
                error = CODEC_ERROR_UNSUPPORTED_FORMAT;
                break;
        }


        ReleaseComponentArrays(allocator, &unpacked_image, channel_count);
    }

cleanup:
    /* Free all wavelets */
    for (int ch = 0; ch < channel_count; ch++) {
        for (int level = 0; level < MAX_WAVELET_COUNT; level++) {
            if (wavelets[ch][level]) {
                DeleteWavelet(allocator, wavelets[ch][level]);
                wavelets[ch][level] = NULL;
            }
        }
    }

    return error;
}
