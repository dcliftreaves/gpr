/* Adapted from Adeel Abbas, gopro/gpr PR #68 (dual Apache-2.0/MIT). */
static int compute_rgb_black_level( const gpr_tuning_info* tuning_info )
{
    const gpr_static_black_level& b = tuning_info->static_black_level;

    int black = ( b.r_black + b.g_r_black + b.g_b_black + b.b_black ) / 4;
    int white = tuning_info->dgain_saturation_level.level_red;

    if( black <= 0 || white <= 0 )
        return 0;

    return (int)( (int64_t)black * 65535 / white );
}

// Guarded like the two functions that use it: RGB_PARAMETERS reaches this file
// through vc5_decoder.h (reading) and the image writer (writing), so with both
// features off the type does not exist and neither does any caller.
#if GPR_READING || GPR_WRITING

// The source's OpcodeList2 GainMap opcodes - one per CFA cell, carrying the lens
// shading (vignetting) correction - reduced to one gain grid per output channel for
// WaveletToRGB. Owns the sample storage that RGB_PARAMETERS::shading_map points at,
// so an instance must outlive the render it is handed to.
//
// This is the RGB path's counterpart to what the DNG writer does with the same
// buffers: the writer hands the opcodes to a DNG consumer to apply, while this
// pipeline has to apply them itself. Without it the corners of a GoPro frame render
// up to ~1.9 EV dark everywhere this path is used.
class rgb_shading_map_tables
{
public:

    rgb_shading_map_tables() : _max_gain( 1.0f ) {}

    // Fills rgb_params->shading_map from the four CFA gain maps. Returns false and
    // leaves the correction disabled - render unchanged - for a source that carries
    // no gain maps, or whose four maps do not agree on a single grid geometry.
    bool build( const gpr_tuning_info* tuning_info, RGB_PARAMETERS* rgb_params );

    // The largest gain any channel asks for, i.e. how much shading the source
    // actually withholds. 1.0 for identity maps, which some cameras ship when a
    // capture mode needs no correction (MISSION 1 PRO 12 MP). Only meaningful
    // after a successful build.
    float max_gain() const { return _max_gain; }

private:

    std::vector<float> _samples[3];     // R, G, B

    float              _max_gain;
};

bool rgb_shading_map_tables::build( const gpr_tuning_info* tuning_info, RGB_PARAMETERS* rgb_params )
{
    memset( &rgb_params->shading_map, 0, sizeof(rgb_params->shading_map) );

    const size_t gain_map_size = tuning_info->gain_map.size;

    if( gain_map_size == 0 )
        return false;

    for( int i = 0; i < 4; i++ )
    {
        if( tuning_info->gain_map.buffers[i] == NULL )
            return false;
    }

    // Which cell of the 2x2 CFA tile each opcode describes comes from its own area
    // spec - the (top,left) parity - never from its position in the list, which
    // follows whatever order the source file used and varies by firmware. Greens sit
    // on the tile's main diagonal for patterns that begin with green, on the
    // anti-diagonal for the rest; this is the same test the DNG writer applies.
    bool greens_on_main_diagonal;
    int  red_top;
    int  red_left;

    switch( tuning_info->pixel_format )
    {
        case PIXEL_FORMAT_GBRG_12:      // G B / R G
        case PIXEL_FORMAT_GBRG_12P:
        case PIXEL_FORMAT_GBRG_14:
        case PIXEL_FORMAT_GBRG_16:
            greens_on_main_diagonal = true;  red_top = 1; red_left = 0;
            break;

        case PIXEL_FORMAT_GRBG_12:
        case PIXEL_FORMAT_GRBG_14:
        case PIXEL_FORMAT_GRBG_16:
            greens_on_main_diagonal=true;red_top=0;red_left=1;break;
        case PIXEL_FORMAT_BGGR_16:
        case PIXEL_FORMAT_BGGR_12:      // B G / G R
        case PIXEL_FORMAT_BGGR_14:
            greens_on_main_diagonal = false; red_top = 1; red_left = 1;
            break;

        default:                        // RGGB: R G / G B
            greens_on_main_diagonal = false; red_top = 0; red_left = 0;
            break;
    }

    uint32 points_v = 0, points_h = 0;
    real64 spacing_v = 0.0, spacing_h = 0.0, origin_v = 0.0, origin_h = 0.0;

    int green_count = 0;

    for( int i = 0; i < 4; i++ )
    {
        // Read through dng_stream, the same reader the writer uses on these buffers,
        // so the byte order matches whatever wrote them by construction.
        dng_stream stream( tuning_info->gain_map.buffers[i], (uint32)gain_map_size );

        stream.Get_uint32();                            // version
        stream.Get_uint32();                            // flags
        stream.Get_uint32();                            // opcode data size

        const int32 area_top  = stream.Get_int32();
        const int32 area_left = stream.Get_int32();
        stream.Get_int32();                             // bottom
        stream.Get_int32();                             // right
        stream.Get_uint32();                            // plane
        stream.Get_uint32();                            // planes
        stream.Get_uint32();                            // row pitch
        stream.Get_uint32();                            // col pitch

        const uint32 map_points_v  = stream.Get_uint32();
        const uint32 map_points_h  = stream.Get_uint32();
        const real64 map_spacing_v = stream.Get_real64();
        const real64 map_spacing_h = stream.Get_real64();
        const real64 map_origin_v  = stream.Get_real64();
        const real64 map_origin_h  = stream.Get_real64();
        const uint32 map_planes    = stream.Get_uint32();

        if( map_points_v == 0 || map_points_h == 0 || map_planes != 1 ||
            map_points_v>1024 || map_points_h>1024 ||
            !isfinite(map_spacing_v) || !isfinite(map_spacing_h) ||
            !isfinite(map_origin_v) || !isfinite(map_origin_h) ||
            map_spacing_v <= 0.0 || map_spacing_h <= 0.0 )
        {
            return false;
        }

        const size_t count = (size_t)map_points_v * (size_t)map_points_h;
        if (gain_map_size<88 || count>(gain_map_size-88)/sizeof(float)) return false;

        if( i == 0 )
        {
            points_v  = map_points_v;  points_h  = map_points_h;
            spacing_v = map_spacing_v; spacing_h = map_spacing_h;
            origin_v  = map_origin_v;  origin_h  = map_origin_h;
        }
        else if( map_points_v  != points_v  || map_points_h  != points_h  ||
                 map_spacing_v != spacing_v || map_spacing_h != spacing_h ||
                 map_origin_v  != origin_v  || map_origin_h  != origin_h )
        {
            // Four maps that do not share a grid cannot be averaged into three
            // channels; leave the render alone rather than guess.
            return false;
        }

        // A CFA source is single-plane, so each opcode carries one map plane; step
        // over any extras rather than assume.
        std::vector<float> gains( count );

        for( size_t k = 0; k < count; k++ )
        {
            gains[k] = stream.Get_real32();

            for( uint32 p = 1; p < map_planes; p++ )
                stream.Get_real32();
        }

        if( ( ( area_top & 1 ) == ( area_left & 1 ) ) == greens_on_main_diagonal )
        {
            // The first green in buffer order rather than an average of the two.
            // The DNG writer copies this same one into both green opcodes (Apple
            // drops the entire gain map when the greens differ), so using it here
            // makes this render agree with what any consumer of the file we write
            // will apply - and keeps the embedded preview byte-identical to a decode
            // of the very GPR it is embedded in, which averaging breaks: the source's
            // greens differ (0.6% on HERO6, up to 7% on MISSION1-50MP) while the
            // written file's are equal by construction.
            if( green_count == 0 )
                _samples[1].swap( gains );

            green_count++;
        }
        else if( ( area_top & 1 ) == red_top && ( area_left & 1 ) == red_left )
        {
            _samples[0].swap( gains );
        }
        else
        {
            _samples[2].swap( gains );
        }
    }

    if( green_count != 2 || _samples[0].empty() || _samples[1].empty() || _samples[2].empty() )
        return false;

    rgb_params->shading_map.samples[0] = &_samples[0][0];
    rgb_params->shading_map.samples[1] = &_samples[1][0];
    rgb_params->shading_map.samples[2] = &_samples[2][0];
    rgb_params->shading_map.points_v   = (int)points_v;
    rgb_params->shading_map.points_h   = (int)points_h;
    rgb_params->shading_map.origin_v   = (float)origin_v;
    rgb_params->shading_map.origin_h   = (float)origin_h;
    rgb_params->shading_map.spacing_v  = (float)spacing_v;
    rgb_params->shading_map.spacing_h  = (float)spacing_h;

    _max_gain = 1.0f;

    for( int c = 0; c < 3; c++ )
    {
        for( size_t k = 0; k < _samples[c].size(); k++ )
        {
            if( _samples[c][k] > _max_gain )
                _max_gain = _samples[c][k];
        }
    }

    return true;
}

#endif // GPR_READING || GPR_WRITING

