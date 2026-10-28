/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "gpr_gvid_reader.h"
#include "gpr_preview.h"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/stat.h>
using Clock=std::chrono::steady_clock;
static double ms(Clock::duration d) { return std::chrono::duration<double,std::milli>(d).count(); }
static ptrdiff_t read_file(void *file,uint8_t *out,size_t bytes) {
    FILE *f=static_cast<FILE *>(file); size_t got=std::fread(out,1,bytes,f);
    return std::ferror(f) ? -1:ptrdiff_t(got);
}
static unsigned integer(const std::string &text) {
    size_t end=0;
    if (text.empty() || text[0]=='-') throw std::runtime_error("invalid unsigned integer");
    unsigned long v=std::stoul(text,&end);
    if (end!=text.size() || v>1000000) throw std::runtime_error("invalid/large integer");
    return unsigned(v);
}
static double percentile(std::vector<double> v,double fraction) {
    if (v.empty()) return 0; std::sort(v.begin(),v.end()); return v[size_t((v.size()-1)*fraction)];
}
int main(int argc,char **argv) {
    try {
        std::string path,directory; unsigned limit=0,runs=1;
        gpr_preview_options options={}; gpr_preview_options_default(&options);
        for (int a=1;a<argc;++a) {
            std::string k=argv[a];
            if (k=="--help") {
                std::cout<<"gpr_preview_app --input clip.gvid [--downsample 4|8|16] [--limit 0] [--runs 1] [--output-dir new_directory]\n";
                return 0;
            }
            if (++a==argc) throw std::runtime_error("missing option value");
            std::string value=argv[a];
            if (k=="--input") path=value;
            else if (k=="--output-dir") directory=value;
            else if (k=="--downsample") options.downsample=integer(value);
            else if (k=="--limit") limit=integer(value);
            else if (k=="--runs") runs=integer(value);
            else throw std::runtime_error("unknown option");
        }
        if (path.empty() || !runs || runs>1000) throw std::runtime_error("input and valid runs required");
        if (!directory.empty() && mkdir(directory.c_str(),0755)) throw std::runtime_error("output directory must be new");
        std::vector<double> decode_times,read_times; size_t inspected=0,rendered=0; bool end_verified=true;
        auto begin=Clock::now(); gpr_preview_info dimensions={};
        for (unsigned run=0;run<runs;++run) {
            std::unique_ptr<FILE,decltype(&std::fclose)> input(std::fopen(path.c_str(),"rb"),std::fclose);
            if (!input) throw std::runtime_error("cannot open recording");
            gpr_gvid_reader *created=nullptr;
            int error=gpr_gvid_reader_create(read_file,input.get(),0,&created);
            if (error) throw std::runtime_error("invalid recording header: "+std::to_string(error));
            std::unique_ptr<gpr_gvid_reader,decltype(&gpr_gvid_reader_close)> reader(created,gpr_gvid_reader_close);
            gpr_gvid_stream_info stream={}; gpr_gvid_reader_info(reader.get(),&stream);
            if (gpr_preview_dimensions(&stream.video,&options,&dimensions)) throw std::runtime_error("unsupported preview options");
            std::vector<uint8_t> rgb(dimensions.row_bytes*dimensions.height);
            size_t count=0;
            for (;;) {
                auto read_begin=Clock::now(); gpr_gvid_frame_view frame={};
                error=gpr_gvid_reader_next(reader.get(),&frame);
                double read_ms=ms(Clock::now()-read_begin);
                if (error==GPR_GVID_DONE) break;
                if (error) throw std::runtime_error("invalid/truncated recording: "+std::to_string(error));
                ++inspected;
                if (!limit || count<limit) {
                    auto start=Clock::now();
                    error=gpr_preview_render(&stream.video,&options,frame.payload,frame.payload_size,
                        rgb.data(),rgb.size(),dimensions.row_bytes,&dimensions);
                    double decode_ms=ms(Clock::now()-start);
                    if (error) throw std::runtime_error("preview decode failed: "+std::to_string(error));
                    read_times.push_back(read_ms); decode_times.push_back(decode_ms); ++rendered;
                    uint32_t crc=gpr_gvid_crc32(0,rgb.data(),rgb.size());
                    if (!directory.empty()) {
                        std::string file=directory+"/run"+std::to_string(run)+"-frame"+std::to_string(frame.index)+".ppm";
                        std::unique_ptr<FILE,decltype(&std::fclose)> out(std::fopen(file.c_str(),"wb"),std::fclose);
                        if (!out || std::fprintf(out.get(),"P6\n%u %u\n255\n",dimensions.width,dimensions.height)<0 ||
                            std::fwrite(rgb.data(),1,rgb.size(),out.get())!=rgb.size() || std::fflush(out.get()))
                            throw std::runtime_error("preview output failed");
                    }
                    std::cout<<"{\"event\":\"preview\",\"run\":"<<run<<",\"index\":"<<frame.index
                        <<",\"timestamp_ns\":"<<frame.timestamp_ns<<",\"width\":"<<dimensions.width
                        <<",\"height\":"<<dimensions.height<<",\"read_verify_ms\":"<<read_ms
                        <<",\"decode_rgb_ms\":"<<decode_ms<<",\"rgb_crc32\":"<<crc<<"}\n";
                }
                ++count;
            }
            if (limit && count<limit) throw std::runtime_error("fewer frames than requested");
            end_verified=end_verified && bool(gpr_gvid_reader_end_verified(reader.get()));
        }
        double elapsed=ms(Clock::now()-begin);
        std::cout<<"{\"event\":\"summary\",\"schema\":\"gpr.stock_preview.v1\",\"runs\":"<<runs
            <<",\"inspected\":"<<inspected<<",\"rendered\":"<<rendered<<",\"width\":"<<dimensions.width
            <<",\"height\":"<<dimensions.height<<",\"decode_rgb_median_ms\":"<<percentile(decode_times,.5)
            <<",\"decode_rgb_p95_ms\":"<<percentile(decode_times,.95)<<",\"read_verify_median_ms\":"<<percentile(read_times,.5)
            <<",\"elapsed_s\":"<<elapsed/1000<<",\"wall_rendered_fps\":"<<rendered*1000/elapsed
            <<",\"complete\":true,\"end_marker_verified\":"<<(end_verified ? "true":"false")<<"}\n";
        return 0;
    } catch (const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
