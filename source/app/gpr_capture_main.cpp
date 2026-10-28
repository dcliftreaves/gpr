/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "gpr_capture.h"
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <fcntl.h>
#include <unistd.h>
#include <sys/resource.h>

using Clock=std::chrono::steady_clock;
static uint64_t now_ns() { return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count()); }
static uint64_t integer(const std::string &s) {
    size_t end=0;
    if (s.empty() || s[0]=='-') throw std::runtime_error("invalid unsigned integer");
    uint64_t v=std::stoull(s,&end);
    if (end!=s.size() || v>UINT32_MAX) throw std::runtime_error("invalid/large integer");
    return v;
}
static uint64_t get(const uint8_t *p,unsigned n) {
    uint64_t v=0; for (unsigned i=0;i<n;++i) v|=uint64_t(p[i])<<(i*8); return v;
}
static std::vector<uint8_t> read_file(const std::string &path,size_t expected) {
    std::ifstream f(path,std::ios::binary|std::ios::ate);
    if (!f || f.tellg()!=std::streamoff(expected)) throw std::runtime_error("input RAW size mismatch: "+path);
    std::vector<uint8_t> out(expected); f.seekg(0);
    if (!f.read(reinterpret_cast<char *>(out.data()),out.size())) throw std::runtime_error("short RAW input");
    for (size_t i=0;i<expected;i+=2)
        if (get(out.data()+i,2)>16383) throw std::runtime_error("input must be 14-bit RGGB in little-endian 16-bit words");
    return out;
}
struct Completion { gpr_capture_completion frame; uint64_t done_ns; };
struct Output {
    int fd=-1;
    bool sync_each=false;
    uint64_t frame_remaining=0;
    std::vector<Completion> completions;
    ~Output() { if (fd>=0) close(fd); }
    static int write(void *user,const uint8_t *p,size_t n) {
        Output &out=*static_cast<Output *>(user);
        const uint8_t *cursor=p; size_t remaining=n;
        while (remaining) {
            ssize_t count=::write(out.fd,cursor,remaining);
            if (count<0 && errno==EINTR) continue;
            if (count<=0) return -1;
            cursor+=count; remaining-=size_t(count);
        }
        if (n==48 && !std::memcmp(p,"FRM3",4)) out.frame_remaining=get(p+24,8)+get(p+32,4);
        else if (out.frame_remaining) {
            if (n>out.frame_remaining) return -1;
            out.frame_remaining-=n;
            if (!out.frame_remaining && out.sync_each && fsync(out.fd)) return -1;
        }
        return 0;
    }
    static void complete(void *user,const gpr_capture_completion *frame) {
        Output &out=*static_cast<Output *>(user);
        out.completions.push_back({*frame,now_ns()});
    }
};
static double percentile(std::vector<double> values,double fraction) {
    if (values.empty()) return 0;
    std::sort(values.begin(),values.end());
    return values[size_t((values.size()-1)*fraction)];
}
static void release_replay_input(void *) {} // Fixtures remain alive through finish.
int main(int argc,char **argv) {
    try {
        gpr_capture_config cfg={}; cfg.video={4096,3072,30,1,4,14,{'R','G','G','B'}};
        cfg.max_inflight=4; cfg.workspace_bytes=192*size_t(1024*1024);
        cfg.metadata="{\"source_kind\":\"raw_fixture_replay\",\"calibration\":\"external_required\"}";
        cfg.metadata_size=std::strlen(static_cast<const char *>(cfg.metadata));
        uint32_t attempts=120,timeout=0;
        bool paced=false,leased=false; Output output;
        std::string path; std::vector<std::string> inputs;
        for (int a=1;a<argc;++a) {
            std::string k=argv[a];
            if (k=="--help") {
                std::cout<<"gpr_capture_app --input frame.raw [--input another.raw] --output clip.gvid\n"
                    "  [--width 4096 --height 3072 --quality 4 --frames 900 --fps-num 30 --fps-den 1]\n"
                    "  [--queue 4 --workspace-mib 192 --submit-timeout-ms 0] [--paced] [--fsync-each] [--leased]\n";
                return 0;
            }
            if (k=="--paced") { paced=true; continue; }
            if (k=="--leased") { leased=true; continue; }
            if (k=="--fsync-each") { output.sync_each=true; continue; }
            if (++a==argc) throw std::runtime_error("missing argument: "+k);
            std::string v=argv[a];
            if (k=="--input") inputs.push_back(v);
            else if (k=="--output") path=v;
            else {
                uint64_t n=integer(v);
                if (k=="--width") cfg.video.width=uint32_t(n);
                else if (k=="--height") cfg.video.height=uint32_t(n);
                else if (k=="--quality") cfg.video.quality=uint32_t(n);
                else if (k=="--fps-num") cfg.video.fps_num=uint32_t(n);
                else if (k=="--fps-den") cfg.video.fps_den=uint32_t(n);
                else if (k=="--queue") cfg.max_inflight=uint32_t(n);
                else if (k=="--workspace-mib") {
                    if (n>2048) throw std::runtime_error("workspace too large");
                    cfg.workspace_bytes=size_t(n)*1024*1024;
                } else if (k=="--submit-timeout-ms") timeout=uint32_t(n);
                else if (k=="--frames") attempts=uint32_t(n);
                else throw std::runtime_error("unknown option: "+k);
            }
        }
        uint8_t header[64];
        if (path.empty() || inputs.empty() || inputs.size()>16 || !attempts || attempts>1000000 ||
            !cfg.max_inflight || cfg.max_inflight>16 ||
            gpr_gvid_write_header(header,&cfg.video,cfg.metadata,cfg.metadata_size)) throw std::runtime_error("invalid configuration");
        cfg.stride_bytes=cfg.video.width*2;
        std::vector<std::vector<uint8_t>> raw;
        for (const auto &input:inputs) raw.push_back(read_file(input,size_t(cfg.stride_bytes)*cfg.video.height));
        for (const char *flag:{"GPR_STREAM_UNPACK","GPR_BAND_STREAM","GPR_CHANNEL_ASM",
                 "GPR_PIN_CHANNELS","GPR_DIRECT_BANDS","GPR_COMPACT_BANDS"}) setenv(flag,"1",1);
        output.completions.reserve(attempts);
        output.fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL,0644);
        if (output.fd<0) throw std::runtime_error("cannot create new output file");
        gpr_capture_callbacks callbacks={Output::write,Output::complete,&output};
        uint64_t setup_begin=now_ns(); gpr_capture *created=nullptr;
        if (gpr_capture_create(&cfg,&callbacks,&created)) throw std::runtime_error("capture create failed");
        std::unique_ptr<gpr_capture,decltype(&gpr_capture_destroy)> capture(created,gpr_capture_destroy);
        uint64_t setup_ns=now_ns()-setup_begin,begin=now_ns(),accepted=0,overruns=0,submit_ns=0;
        for (uint64_t i=0;i<attempts;++i) {
            uint64_t due=begin+i*1000000000ULL*cfg.video.fps_den/cfg.video.fps_num;
            if (paced) std::this_thread::sleep_until(Clock::time_point(std::chrono::duration_cast<Clock::duration>(std::chrono::nanoseconds(due))));
            auto &input=raw[i%raw.size()];
            std::string metadata="{\"source_index\":"+std::to_string(i%raw.size())+",\"attempt_index\":"+std::to_string(i)+"}";
            gpr_capture_frame frame={input.data(),input.size(),accepted,now_ns(),metadata.data(),metadata.size()};
            if (leased) frame.release=release_replay_input;
            uint64_t start=now_ns(); int error=gpr_capture_submit(capture.get(),&frame,timeout);
            submit_ns+=now_ns()-start;
            if (error==GPR_CAPTURE_BUSY) ++overruns;
            else if (error) throw std::runtime_error("capture submit failed: "+std::to_string(error));
            else ++accepted;
        }
        int error=gpr_capture_finish(capture.get());
        uint64_t finish=now_ns();
        if (error) throw std::runtime_error("capture finish failed: "+std::to_string(error));
        if (fsync(output.fd)) throw std::runtime_error("final fsync failed");
        uint64_t durable=now_ns();
        gpr_capture_stats stats={}; gpr_capture_get_stats(capture.get(),&stats);
        struct rusage usage={}; getrusage(RUSAGE_SELF,&usage);
        uint64_t peak_rss_bytes=uint64_t(usage.ru_maxrss);
#if !defined(__APPLE__)
        peak_rss_bytes*=1024;
#endif
        std::vector<double> encode,latency,write; size_t missed=0;
        for (const auto &r:output.completions) {
            double latency_s=double(r.done_ns-r.frame.timestamp_ns)*1e-9;
            bool late=uint64_t(r.done_ns-r.frame.timestamp_ns)>1000000000ULL*cfg.video.fps_den/cfg.video.fps_num;
            missed+=late; encode.push_back(r.frame.encode_ns*1e-6); latency.push_back(latency_s*1000); write.push_back(r.frame.write_ns*1e-6);
            std::cout<<"{\"event\":\"frame\",\"index\":"<<r.frame.index<<",\"timestamp_ns\":"<<r.frame.timestamp_ns
                <<",\"bytes\":"<<r.frame.payload_bytes<<",\"encode_ms\":"<<r.frame.encode_ns*1e-6
                <<",\"write_ms\":"<<r.frame.write_ns*1e-6<<",\"capture_to_written_ms\":"<<latency_s*1000
                <<",\"deadline_missed\":"<<(late ? "true":"false")<<"}\n";
        }
        std::cout<<"{\"event\":\"summary\",\"schema\":\"gpr.capture_replay.v1\",\"attempts\":"<<attempts
            <<",\"accepted\":"<<accepted<<",\"written\":"<<stats.written<<",\"overruns\":"<<overruns
            <<",\"queue\":"<<cfg.max_inflight<<",\"inflight_high_water\":"<<stats.inflight_high_water
            <<",\"leased\":"<<(leased ? "true":"false")
            <<",\"fps_num\":"<<cfg.video.fps_num<<",\"fps_den\":"<<cfg.video.fps_den<<",\"quality\":"<<cfg.video.quality
            <<",\"buffered_fps\":"<<double(stats.written)*1e9/(finish-begin)
            <<",\"durable_fps\":"<<double(stats.written)*1e9/(durable-begin)
            <<",\"encode_median_ms\":"<<percentile(encode,.5)<<",\"write_p95_ms\":"<<percentile(write,.95)
            <<",\"capture_to_written_p95_ms\":"<<percentile(latency,.95)<<",\"deadline_misses\":"<<missed
            <<",\"final_fsync_s\":"<<(durable-finish)*1e-9<<",\"submit_s\":"<<submit_ns*1e-9
            <<",\"queue_wait_s\":"<<stats.submit_wait_ns*1e-9<<",\"setup_s\":"<<setup_ns*1e-9
            <<",\"workspace_peak_bytes\":"<<stats.workspace_peak_bytes<<",\"workspace_fallback_peak_bytes\":"<<stats.workspace_fallback_peak_bytes
            <<",\"peak_rss_bytes\":"<<peak_rss_bytes
            <<",\"payload_bytes\":"<<stats.payload_bytes<<",\"complete\":true}\n";
        return 0;
    } catch (const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
