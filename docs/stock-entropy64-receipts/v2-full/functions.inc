#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "headers.h"
static inline void write_bits(uint8_t **p,uint32_t bits){uint32_t v=__builtin_bswap32(bits);memcpy(*p,&v,4);}
static CODEC_ERROR baseline_incremental(BITSTREAM *stream, ENCODER_CODESET *codeset, PIXEL *data,
    DIMENSION width, DIMENSION height, DIMENSION pitch, uint32_t *pending, bool final)
{
	CODEC_ERROR error = CODEC_ERROR_OKAY;

	int row_padding;
	int row = 0;
	//int column = 0;
	//size_t index = 0;

	// The encoder uses the codebooks for magnitudes and runs of zeros
	const MAGS_TABLE *mags_table = codeset->mags_table;
	const RUNS_TABLE *runs_table = codeset->runs_table;
	uint32_t runs_table_length = runs_table->length;
	RLC *rlc = (RLC *)((uint8_t *)runs_table + sizeof(RUNS_TABLE));

	// The band is terminated by the band end codeword in the codebook
	const CODEBOOK *codebook = codeset->codebook;

	PIXEL *rowptr = data;

	// Convert the pitch to units of pixels
	assert((pitch % sizeof(PIXEL)) == 0);
	pitch /= sizeof(PIXEL);

	// Check that the band dimensions are reasonable
	assert(width <= pitch);

	// Compute the number of values of padding at the end of each row
	// Physical cache-line padding is not a logical coefficient in the stream.
	row_padding = 0;

	VLE *mags_table_entry = (VLE *)((uint8_t *)mags_table + sizeof(MAGS_TABLE));

    uint64_t accumulator = (uint64_t)stream->buffer >> (32 - stream->count);
    unsigned occupied = stream->count;
    
    struct _stream *bit_stream = stream->stream;
    
    int mags_table_length_minus_1 = mags_table->length - 1;
    
    uint8_t* stream_buffer      = (uint8_t *)bit_stream->location.memory.buffer + bit_stream->byte_count;
    uint8_t* stream_buffer_orig = stream_buffer;
    
	uint32_t count = pending ? *pending : 0;
	for (row = 0; row < height; row++)
	{
		uint32_t index = 0;			// Start at the beginning of the row

		// Search the row for runs of zeros and nonzero values
		while (1)
		{
			// Loop invariant
			assert(index < width);
            if (count == 0 && index + 4 <= width && rowptr[index+3] != 0) {
                // A nonzero final value bounds every zero run to three.
                // Four independent table loads precede the serial packing.
                uint64_t c0 = codeset->signed_codes[(uint16_t)rowptr[index]];
                uint64_t c1 = codeset->signed_codes[(uint16_t)rowptr[index+1]];
                uint64_t c2 = codeset->signed_codes[(uint16_t)rowptr[index+2]];
                uint64_t c3 = codeset->signed_codes[(uint16_t)rowptr[index+3]];
                unsigned n0=c0>>32, n1=c1>>32, n2=c2>>32, n3=c3>>32;
                unsigned length=n0+n1+n2+n3;
                if (length <= 32) {
                    uint64_t bits01=((uint64_t)(uint32_t)c0<<n1)|(uint32_t)c1;
                    uint64_t bits23=((uint64_t)(uint32_t)c2<<n3)|(uint32_t)c3;
                    uint64_t bits=(bits01<<(n2+n3))|bits23;
                    accumulator=(accumulator<<length)|bits;
                    occupied+=length;
                    if (occupied>=32) {
                        occupied-=32;
                        write_bits(&stream_buffer,(uint32_t)(accumulator>>occupied));
                        stream_buffer+=4;
                    }
                } else {
#define APPEND_TOKEN(c) do { \
    unsigned length = (unsigned)((c) >> 32); \
    accumulator = (accumulator << length) | (uint32_t)(c); \
    occupied += length; \
    if (occupied >= 32) { \
        occupied -= 32; \
        write_bits(&stream_buffer, (uint32_t)(accumulator >> occupied)); \
        stream_buffer += 4; \
    } \
} while (0)
                APPEND_TOKEN(c0);
                APPEND_TOKEN(c1);
                APPEND_TOKEN(c2);
                APPEND_TOKEN(c3);
#undef APPEND_TOKEN
                }
                index += 4;
                if (index == width) break;
                continue;
            }
            
            {
                PIXEL* start = rowptr + index;
                PIXEL* end   = rowptr + width;
                
                for (; start != end && *(start) == 0; start++)
                {
                    
                }
                
                uint32_t x = start - (rowptr + index);
                    
                index += x;
                count += x;
            }
            
			// Need to output a value?
			if (index < width)
			{
                while (count > 0)
                {
                    if( count < 12 )
                    {
                        // Short zero runs are leading zero bits of the next
                        // codeword; consume both with one reservoir update.
                        break;
                    }
                    else
                    {
                        uint32_t count_index = minimum(count, runs_table_length - 1);
                        assert(count_index < runs_table->length);
                        
                        RLC rlc_val = rlc[count_index];
                        
                        accumulator = (accumulator << rlc_val.size) | rlc_val.bits;
                        occupied += rlc_val.size;
                        if (occupied >= 32) {
                            occupied -= 32;
                            write_bits(&stream_buffer, (uint32_t)(accumulator >> occupied));
                            stream_buffer += 4;
                        }
                        
                        // Reduce the length of the run by the amount output
                        count -= rlc_val.count;
                    }
                }
                
                
				// The value zero is run length coded and handled by another routine
				{
					PIXEL value = rowptr[index++];
					assert(value != 0);
                    
                    uint64_t code = codeset->signed_codes[(uint16_t)value];
                    unsigned size = (unsigned)(code >> 32) + count;
                    if (size > 32) {
                        accumulator <<= count;
                        occupied += count;
                        if (occupied >= 32) {
                            occupied -= 32;
                            write_bits(&stream_buffer, (uint32_t)(accumulator >> occupied));
                            stream_buffer += 4;
                        }
                        size -= count;
                    }
                    count = 0;
                    accumulator = (accumulator << size) | (uint32_t)code;
                    occupied += size;
                    if (occupied >= 32) {
                        occupied -= 32;
                        write_bits(&stream_buffer, (uint32_t)(accumulator >> occupied));
                        stream_buffer += 4;
                    }
				}
			}

			// Add the end of row padding to the encoded length
			if (index == width)
            {
                count += row_padding;
                break;
            }
		}

		// Should have processed the entire row
		assert(index == width);

		// Advance to the next row
		rowptr += pitch;
	}

	stream->count = occupied;
	stream->buffer = (uint32_t)(accumulator << (32 - occupied));
    bit_stream->byte_count += (stream_buffer - stream_buffer_orig);
    if (pending) *pending = count;
    if (!final) return CODEC_ERROR_OKAY;
    
	// // Need to output a pending run of zeros?
	if (count > 0)
	{
		error = PutZeros(stream, runs_table, count);
		if (error != CODEC_ERROR_OKAY) {
			return error;
		}
	}

	// Insert the special codeword that marks the end of the highpass band
	error = PutSpecial(stream, codebook, SPECIAL_MARKER_BAND_END);

	return error;
}

static CODEC_ERROR candidate_incremental(BITSTREAM *stream, ENCODER_CODESET *codeset, PIXEL *data,
    DIMENSION width, DIMENSION height, DIMENSION pitch, uint32_t *pending, bool final)
{
	CODEC_ERROR error = CODEC_ERROR_OKAY;

	int row_padding;
	int row = 0;
	//int column = 0;
	//size_t index = 0;

	// The encoder uses the codebooks for magnitudes and runs of zeros
	const MAGS_TABLE *mags_table = codeset->mags_table;
	const RUNS_TABLE *runs_table = codeset->runs_table;
	uint32_t runs_table_length = runs_table->length;
	RLC *rlc = (RLC *)((uint8_t *)runs_table + sizeof(RUNS_TABLE));

	// The band is terminated by the band end codeword in the codebook
	const CODEBOOK *codebook = codeset->codebook;

	PIXEL *rowptr = data;

	// Convert the pitch to units of pixels
	assert((pitch % sizeof(PIXEL)) == 0);
	pitch /= sizeof(PIXEL);

	// Check that the band dimensions are reasonable
	assert(width <= pitch);

	// Compute the number of values of padding at the end of each row
	// Physical cache-line padding is not a logical coefficient in the stream.
	row_padding = 0;

	VLE *mags_table_entry = (VLE *)((uint8_t *)mags_table + sizeof(MAGS_TABLE));

    uint64_t accumulator = (uint64_t)stream->buffer >> (32 - stream->count);
    unsigned occupied = stream->count;
    
    struct _stream *bit_stream = stream->stream;
    
    int mags_table_length_minus_1 = mags_table->length - 1;
    
    uint8_t* stream_buffer      = (uint8_t *)bit_stream->location.memory.buffer + bit_stream->byte_count;
    uint8_t* stream_buffer_orig = stream_buffer;
    
	uint32_t count = pending ? *pending : 0;
	for (row = 0; row < height; row++)
	{
		uint32_t index = 0;			// Start at the beginning of the row

		// Search the row for runs of zeros and nonzero values
		while (1)
		{
			// Loop invariant
			assert(index < width);
            if (count == 0 && index + 4 <= width && rowptr[index+3] != 0) {
                // A nonzero final value bounds every zero run to three.
                // Four independent table loads precede the serial packing.
                uint64_t c0 = codeset->signed_codes[(uint16_t)rowptr[index]];
                uint64_t c1 = codeset->signed_codes[(uint16_t)rowptr[index+1]];
                uint64_t c2 = codeset->signed_codes[(uint16_t)rowptr[index+2]];
                uint64_t c3 = codeset->signed_codes[(uint16_t)rowptr[index+3]];
                unsigned n0=c0>>32, n1=c1>>32, n2=c2>>32, n3=c3>>32;
                unsigned length=n0+n1+n2+n3;
                if (length <= 64) {
                    uint64_t bits01=((uint64_t)(uint32_t)c0<<n1)|(uint32_t)c1;
                    uint64_t bits23=((uint64_t)(uint32_t)c2<<n3)|(uint32_t)c3;
                    uint64_t bits=(bits01<<(n2+n3))|bits23;
                    unsigned total=occupied+length;
                    if (total>=32) {
                        unsigned rest=total-32;
                        write_bits(&stream_buffer,(uint32_t)((accumulator<<(32-occupied))|(rest==64 ? UINT64_C(0):(bits>>rest))));
                        stream_buffer+=4;
                        if (rest>=32) {
                            rest-=32;
                            write_bits(&stream_buffer,(uint32_t)(bits>>rest));
                            stream_buffer+=4;
                        }
                        accumulator=bits;
                        occupied=rest;
                    } else {
                        accumulator=(accumulator<<length)|bits;
                        occupied=total;
                    }
                } else {
#define APPEND_TOKEN(c) do { \
    unsigned length = (unsigned)((c) >> 32); \
    accumulator = (accumulator << length) | (uint32_t)(c); \
    occupied += length; \
    if (occupied >= 32) { \
        occupied -= 32; \
        write_bits(&stream_buffer, (uint32_t)(accumulator >> occupied)); \
        stream_buffer += 4; \
    } \
} while (0)
                APPEND_TOKEN(c0);
                APPEND_TOKEN(c1);
                APPEND_TOKEN(c2);
                APPEND_TOKEN(c3);
#undef APPEND_TOKEN
                }
                index += 4;
                if (index == width) break;
                continue;
            }
            
            {
                PIXEL* start = rowptr + index;
                PIXEL* end   = rowptr + width;
                
                for (; start != end && *(start) == 0; start++)
                {
                    
                }
                
                uint32_t x = start - (rowptr + index);
                    
                index += x;
                count += x;
            }
            
			// Need to output a value?
			if (index < width)
			{
                while (count > 0)
                {
                    if( count < 12 )
                    {
                        // Short zero runs are leading zero bits of the next
                        // codeword; consume both with one reservoir update.
                        break;
                    }
                    else
                    {
                        uint32_t count_index = minimum(count, runs_table_length - 1);
                        assert(count_index < runs_table->length);
                        
                        RLC rlc_val = rlc[count_index];
                        
                        accumulator = (accumulator << rlc_val.size) | rlc_val.bits;
                        occupied += rlc_val.size;
                        if (occupied >= 32) {
                            occupied -= 32;
                            write_bits(&stream_buffer, (uint32_t)(accumulator >> occupied));
                            stream_buffer += 4;
                        }
                        
                        // Reduce the length of the run by the amount output
                        count -= rlc_val.count;
                    }
                }
                
                
				// The value zero is run length coded and handled by another routine
				{
					PIXEL value = rowptr[index++];
					assert(value != 0);
                    
                    uint64_t code = codeset->signed_codes[(uint16_t)value];
                    unsigned size = (unsigned)(code >> 32) + count;
                    if (size > 32) {
                        accumulator <<= count;
                        occupied += count;
                        if (occupied >= 32) {
                            occupied -= 32;
                            write_bits(&stream_buffer, (uint32_t)(accumulator >> occupied));
                            stream_buffer += 4;
                        }
                        size -= count;
                    }
                    count = 0;
                    accumulator = (accumulator << size) | (uint32_t)code;
                    occupied += size;
                    if (occupied >= 32) {
                        occupied -= 32;
                        write_bits(&stream_buffer, (uint32_t)(accumulator >> occupied));
                        stream_buffer += 4;
                    }
				}
			}

			// Add the end of row padding to the encoded length
			if (index == width)
            {
                count += row_padding;
                break;
            }
		}

		// Should have processed the entire row
		assert(index == width);

		// Advance to the next row
		rowptr += pitch;
	}

	stream->count = occupied;
	stream->buffer = (uint32_t)(accumulator << (32 - occupied));
    bit_stream->byte_count += (stream_buffer - stream_buffer_orig);
    if (pending) *pending = count;
    if (!final) return CODEC_ERROR_OKAY;
    
	// // Need to output a pending run of zeros?
	if (count > 0)
	{
		error = PutZeros(stream, runs_table, count);
		if (error != CODEC_ERROR_OKAY) {
			return error;
		}
	}

	// Insert the special codeword that marks the end of the highpass band
	error = PutSpecial(stream, codebook, SPECIAL_MARKER_BAND_END);

	return error;
}
