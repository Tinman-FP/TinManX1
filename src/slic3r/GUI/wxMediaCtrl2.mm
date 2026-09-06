//
//  wxMediaCtrl2.m
//  OrcaSlicer
//
//  Created by cmguo on 2021/12/7.
//

#import "wxMediaCtrl2.h"
#import "wx/mediactrl.h"
#include <boost/log/trivial.hpp>

#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import "BambuPlayer/BambuPlayer.h"
#import "../Utils/NetworkAgent.hpp"

#include <stdlib.h>
#include <dlfcn.h>
#include <exception>

namespace {

void log_player_exception(const char* operation, const char* detail)
{
    BOOST_LOG_TRIVIAL(error) << "BambuPlayer " << operation << " failed: " << (detail ? detail : "unknown exception");
}

} // namespace

@interface TinManRTSPPlayer : NSObject {
    NSView *_imageView;
    NSTask *_task;
    NSPipe *_outputPipe;
    NSPipe *_errorPipe;
    NSCondition *_firstFrameCondition;
    NSMutableData *_jpegBuffer;
    NSMutableData *_errorBuffer;
    NSSize _videoSize;
    BOOL _firstFrameReady;
    BOOL _stopping;
}

- (instancetype)initWithImageView:(NSView *)imageView;
- (int)openStream:(NSString *)streamURL;
- (void)close;
- (NSSize)videoSize;

@end

@implementation TinManRTSPPlayer

static NSString *TinManRTSPBridgePath()
{
    NSMutableArray<NSString *> *candidates = [NSMutableArray array];
    NSString *bundled = [[NSBundle mainBundle] pathForResource:@"tinman-rtsp-bridge"
                                                        ofType:nil
                                                   inDirectory:@"orcaslicer_codex/tools"];
    if (bundled)
        [candidates addObject:bundled];
    [candidates addObject:@"/opt/homebrew/bin/ffmpeg"];
    [candidates addObject:@"/usr/local/bin/ffmpeg"];

    for (NSString *candidate in candidates) {
        if ([[NSFileManager defaultManager] isExecutableFileAtPath:candidate])
            return candidate;
    }
    return nil;
}

- (instancetype)initWithImageView:(NSView *)imageView
{
    self = [super init];
    if (self) {
        _imageView = imageView;
        _firstFrameCondition = [[NSCondition alloc] init];
        _videoSize = NSMakeSize(0, 0);
    }
    return self;
}

- (void)dealloc
{
    [self close];
    [_firstFrameCondition release];
    [super dealloc];
}

- (void)publishJPEGFrame:(NSData *)jpeg
{
    @autoreleasepool {
        NSImage *image = [[[NSImage alloc] initWithData:jpeg] autorelease];
        if (!image)
            return;

        NSRect proposedRect = NSMakeRect(0, 0, image.size.width, image.size.height);
        CGImageRef cgImage = [image CGImageForProposedRect:&proposedRect context:nil hints:nil];
        if (!cgImage)
            return;
        CGImageRetain(cgImage);

        [_firstFrameCondition lock];
        _videoSize = image.size;
        if (!_firstFrameReady) {
            _firstFrameReady = YES;
            [_firstFrameCondition broadcast];
        }
        [_firstFrameCondition unlock];

        NSView *imageView = _imageView;
        dispatch_async(dispatch_get_main_queue(), ^{
            imageView.layer.contentsGravity = kCAGravityResizeAspect;
            imageView.layer.contents = (id)cgImage;
            CGImageRelease(cgImage);
        });
    }
}

- (void)consumeOutput:(NSData *)data
{
    if (data.length == 0 || _stopping)
        return;

    @synchronized (self) {
        [_jpegBuffer appendData:data];
        static const unsigned char soiBytes[] = {0xff, 0xd8};
        static const unsigned char eoiBytes[] = {0xff, 0xd9};
        NSData *soi = [NSData dataWithBytesNoCopy:(void *)soiBytes length:sizeof(soiBytes) freeWhenDone:NO];
        NSData *eoi = [NSData dataWithBytesNoCopy:(void *)eoiBytes length:sizeof(eoiBytes) freeWhenDone:NO];

        while (_jpegBuffer.length >= 4) {
            NSRange start = [_jpegBuffer rangeOfData:soi options:0 range:NSMakeRange(0, _jpegBuffer.length)];
            if (start.location == NSNotFound) {
                if (_jpegBuffer.length > 1)
                    [_jpegBuffer replaceBytesInRange:NSMakeRange(0, _jpegBuffer.length - 1) withBytes:nullptr length:0];
                break;
            }
            if (start.location > 0)
                [_jpegBuffer replaceBytesInRange:NSMakeRange(0, start.location) withBytes:nullptr length:0];

            NSRange searchRange = NSMakeRange(2, _jpegBuffer.length - 2);
            NSRange end = [_jpegBuffer rangeOfData:eoi options:0 range:searchRange];
            if (end.location == NSNotFound)
                break;

            const NSUInteger frameLength = NSMaxRange(end);
            NSData *frame = [NSData dataWithBytes:_jpegBuffer.bytes length:frameLength];
            [_jpegBuffer replaceBytesInRange:NSMakeRange(0, frameLength) withBytes:nullptr length:0];
            [self publishJPEGFrame:frame];
        }

        if (_jpegBuffer.length > 8 * 1024 * 1024)
            [_jpegBuffer setLength:0];
    }
}

- (int)openStream:(NSString *)streamURL
{
    [self close];

    NSString *bridgePath = TinManRTSPBridgePath();
    if (!bridgePath) {
        BOOST_LOG_TRIVIAL(error) << "Direct RTSP player is missing tinman-rtsp-bridge";
        return 105;
    }

    _stopping = NO;
    _firstFrameReady = NO;
    _videoSize = NSMakeSize(0, 0);
    _jpegBuffer = [[NSMutableData alloc] init];
    _errorBuffer = [[NSMutableData alloc] init];
    _outputPipe = [[NSPipe alloc] init];
    _errorPipe = [[NSPipe alloc] init];
    _task = [[NSTask alloc] init];
    _task.launchPath = bridgePath;
    _task.arguments = @[
        @"-nostdin", @"-hide_banner", @"-loglevel", @"warning",
        @"-rtsp_transport", @"tcp",
        @"-i", streamURL, @"-map", @"0:v:0", @"-an",
        @"-vf", @"fps=10,scale=960:-2", @"-c:v", @"mjpeg", @"-q:v", @"5",
        @"-f", @"image2pipe", @"pipe:1"
    ];
    _task.standardOutput = _outputPipe;
    _task.standardError = _errorPipe;

    TinManRTSPPlayer *player = self;
    _outputPipe.fileHandleForReading.readabilityHandler = ^(NSFileHandle *handle) {
        NSData *data = handle.availableData;
        if (data.length > 0)
            [player consumeOutput:data];
    };
    _errorPipe.fileHandleForReading.readabilityHandler = ^(NSFileHandle *handle) {
        NSData *data = handle.availableData;
        if (data.length > 0) {
            @synchronized (player) {
                [player->_errorBuffer appendData:data];
                if (player->_errorBuffer.length > 32 * 1024)
                    [player->_errorBuffer replaceBytesInRange:NSMakeRange(0, player->_errorBuffer.length - 32 * 1024)
                                                     withBytes:nullptr length:0];
            }
        }
    };
    _task.terminationHandler = ^(NSTask *task) {
        [player->_firstFrameCondition lock];
        [player->_firstFrameCondition broadcast];
        [player->_firstFrameCondition unlock];
    };

    @try {
        [_task launch];
    } @catch (NSException *exception) {
        BOOST_LOG_TRIVIAL(error) << "Direct RTSP player launch failed: " << [[exception description] UTF8String];
        [self close];
        return 105;
    }

    [_firstFrameCondition lock];
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:12.0];
    while (!_firstFrameReady && _task.running) {
        if (![_firstFrameCondition waitUntilDate:deadline])
            break;
    }
    const BOOL ready = _firstFrameReady;
    [_firstFrameCondition unlock];

    if (!ready) {
        NSString *details = nil;
        @synchronized (self) {
            details = [[[NSString alloc] initWithData:_errorBuffer encoding:NSUTF8StringEncoding] autorelease];
        }
        BOOST_LOG_TRIVIAL(error) << "Direct RTSP player did not receive a frame: "
                                 << (details ? [details UTF8String] : "no decoder details");
        [self close];
        return -54;
    }

    BOOST_LOG_TRIVIAL(info) << "Direct RTSP player received first frame at "
                            << static_cast<int>(_videoSize.width) << "x" << static_cast<int>(_videoSize.height);
    return 0;
}

- (void)close
{
    _stopping = YES;
    if (_outputPipe)
        _outputPipe.fileHandleForReading.readabilityHandler = nil;
    if (_errorPipe)
        _errorPipe.fileHandleForReading.readabilityHandler = nil;
    if (_task) {
        _task.terminationHandler = nil;
        if (_task.running)
            [_task terminate];
    }

    [_task release];
    [_outputPipe release];
    [_errorPipe release];
    [_jpegBuffer release];
    [_errorBuffer release];
    _task = nil;
    _outputPipe = nil;
    _errorPipe = nil;
    _jpegBuffer = nil;
    _errorBuffer = nil;
}

- (NSSize)videoSize
{
    [_firstFrameCondition lock];
    NSSize size = _videoSize;
    [_firstFrameCondition unlock];
    return size;
}

@end

wxDEFINE_EVENT(EVT_MEDIA_CTRL_STAT, wxCommandEvent);

#define BAMBU_DYNAMIC

void wxMediaCtrl2::bambu_log(void const * ctx, int level, char const * msg)
{
    if (level == 1) {
        wxString msg2(msg);
        if (msg2.EndsWith("]")) {
            int n = msg2.find_last_of('[');
            if (n != wxString::npos) {
                long val = 0;
                wxMediaCtrl2 * ctrl = (wxMediaCtrl2 *) ctx;
                if (msg2.SubString(n + 1, msg2.Length() - 2).ToLong(&val))
                    ctrl->m_error = (int) val;
            }
        } else if (strstr(msg, "stat_log")) {
            wxMediaCtrl2 * ctrl = (wxMediaCtrl2 *) ctx;
            wxCommandEvent evt(EVT_MEDIA_CTRL_STAT);
            evt.SetEventObject(ctrl);
            evt.SetString(strchr(msg, ' ') + 1);
            wxPostEvent(ctrl, evt);
        }
    } else if (level < 0) {
        wxMediaCtrl2 * ctrl = (wxMediaCtrl2 *) ctx;
        ctrl->NotifyStopped();
    }
    BOOST_LOG_TRIVIAL(info) << msg;
}

wxMediaCtrl2::wxMediaCtrl2(wxWindow * parent)
    : wxWindow(parent, wxID_ANY, wxDefaultPosition, wxDefaultSize)
{
    NSView * imageView = (NSView *) GetHandle();
    imageView.layer = [[CALayer alloc] init];
    CGColorRef color = CGColorCreateGenericRGB(0, 0, 0, 1.0f);
    imageView.layer.backgroundColor = color;
    CGColorRelease(color);
    imageView.wantsLayer = YES;
    create_player();
}

wxMediaCtrl2::~wxMediaCtrl2()
{
    TinManRTSPPlayer *directPlayer = (TinManRTSPPlayer *)m_direct_player;
    [directPlayer release];
    m_direct_player = nullptr;

    BambuPlayer * player = (BambuPlayer *) m_player;
    try {
        @try {
            [player dealloc];
        } @catch (NSException* exception) {
            log_player_exception("dealloc", [[exception description] UTF8String]);
        }
    } catch (const std::exception& exception) {
        log_player_exception("dealloc", exception.what());
    } catch (...) {
        log_player_exception("dealloc", nullptr);
    }
}

void wxMediaCtrl2::create_player()
{
	auto module = Slic3r::NetworkAgent::get_bambu_source_entry();
	if (!module) {
		//not ready yet
		BOOST_LOG_TRIVIAL(info) << __FUNCTION__ << "Network plugin not ready currently!";
		return;
	}
    Class cls = (__bridge Class) dlsym(module, "OBJC_CLASS_$_BambuPlayer");
    if (cls == nullptr) {
        m_error = -2;
        return;
    }
    NSView * imageView = (NSView *) GetHandle();
    BambuPlayer * player = [cls alloc];
    [player initWithImageView: imageView];
    [player setLogger: bambu_log withContext: this];
    m_player = player;
}

void wxMediaCtrl2::Load(wxURI url)
{
	if (m_direct_player) {
        [(TinManRTSPPlayer *)m_direct_player close];
        m_direct_stream_active = false;
    }
	if (!m_player) {
		create_player();
		if (!m_player) {
			BOOST_LOG_TRIVIAL(info) << __FUNCTION__ << ": create_player failed currently!";
			return;
		}
	}

    BambuPlayer * player = (BambuPlayer *) m_player;
    if (player) {
        m_error = 0;
        try {
            @try {
                [player close];
                m_error = [player open: url.BuildURI().ToUTF8()];
            } @catch (NSException* exception) {
                log_player_exception("open", [[exception description] UTF8String]);
                m_error = -3;
            }
        } catch (const std::exception& exception) {
            log_player_exception("open", exception.what());
            m_error = -3;
        } catch (...) {
            log_player_exception("open", nullptr);
            m_error = -3;
        }
    }
    wxMediaEvent event(wxEVT_MEDIA_STATECHANGED);
    event.SetId(GetId());
    event.SetEventObject(this);
    wxPostEvent(this, event);
}

void wxMediaCtrl2::LoadDirectStream(wxString const & url)
{
    BambuPlayer *player = (BambuPlayer *)m_player;
    if (player) {
        try {
            @try {
                [player close];
            } @catch (NSException *exception) {
                log_player_exception("close before direct RTSP", [[exception description] UTF8String]);
            }
        } catch (const std::exception& exception) {
            log_player_exception("close before direct RTSP", exception.what());
        } catch (...) {
            log_player_exception("close before direct RTSP", nullptr);
        }
    }

    if (!m_direct_player)
        m_direct_player = [[TinManRTSPPlayer alloc] initWithImageView:(NSView *)GetHandle()];

    m_direct_stream_active = true;
    m_state = wxMEDIASTATE_STOPPED;
    m_error = [(TinManRTSPPlayer *)m_direct_player openStream:[NSString stringWithUTF8String:url.ToUTF8().data()]];
    const NSSize size = [(TinManRTSPPlayer *)m_direct_player videoSize];
    if (size.width > 0 && size.height > 0)
        m_video_size = {static_cast<int>(size.width), static_cast<int>(size.height)};

    wxMediaEvent event(wxEVT_MEDIA_STATECHANGED);
    event.SetId(GetId());
    event.SetEventObject(this);
    wxPostEvent(this, event);
}

void wxMediaCtrl2::Play()
{
	if (m_direct_stream_active) {
        if (m_error != 0) {
            NotifyStopped();
            return;
        }
        if (m_state != wxMEDIASTATE_PLAYING) {
            m_state = wxMEDIASTATE_PLAYING;
            wxMediaEvent event(wxEVT_MEDIA_STATECHANGED);
            event.SetId(GetId());
            event.SetEventObject(this);
            wxPostEvent(this, event);
        }
        return;
    }
	if (!m_player) {
		create_player();
		if (!m_player) {
			BOOST_LOG_TRIVIAL(info) << __FUNCTION__ << ": create_player failed currently!";
			return;
		}
    }
    BambuPlayer * player2 = (BambuPlayer *) m_player;
    try {
        @try {
            m_error = [player2 play];
        } @catch (NSException* exception) {
            log_player_exception("play", [[exception description] UTF8String]);
            m_error = -3;
        }
    } catch (const std::exception& exception) {
        log_player_exception("play", exception.what());
        m_error = -3;
    } catch (...) {
        log_player_exception("play", nullptr);
        m_error = -3;
    }
    if (m_error != 0) {
        NotifyStopped();
        return;
    }
    if (m_state != wxMEDIASTATE_PLAYING) {
        m_state = wxMEDIASTATE_PLAYING;
        wxMediaEvent event(wxEVT_MEDIA_STATECHANGED);
        event.SetId(GetId());
        event.SetEventObject(this);
        wxPostEvent(this, event);
    }
}

void wxMediaCtrl2::Stop()
{
	if (m_direct_stream_active) {
        [(TinManRTSPPlayer *)m_direct_player close];
        m_direct_stream_active = false;
        NotifyStopped();
        return;
    }
	if (!m_player) {
		create_player();
		if (!m_player) {
			BOOST_LOG_TRIVIAL(info) << __FUNCTION__ << ": create_player failed currently!";
			return;
		}
    }
    BambuPlayer * player2 = (BambuPlayer *) m_player;
    try {
        @try {
            [player2 close];
        } @catch (NSException* exception) {
            log_player_exception("close", [[exception description] UTF8String]);
            m_error = -3;
        }
    } catch (const std::exception& exception) {
        log_player_exception("close", exception.what());
        m_error = -3;
    } catch (...) {
        log_player_exception("close", nullptr);
        m_error = -3;
    }
    NotifyStopped();
}

void wxMediaCtrl2::NotifyStopped()
{
    if (m_state != wxMEDIASTATE_STOPPED) {
        m_state = wxMEDIASTATE_STOPPED;
        wxMediaEvent event(wxEVT_MEDIA_STATECHANGED);
        event.SetId(GetId());
        event.SetEventObject(this);
        wxPostEvent(this, event);
    }
}

wxMediaState wxMediaCtrl2::GetState() const
{
    return m_state;
}

wxSize wxMediaCtrl2::GetVideoSize() const
{
    if (m_direct_stream_active)
        return m_video_size;

    BambuPlayer * player2 = (BambuPlayer *) m_player;
    if (player2) {
        NSSize size = [player2 videoSize];
        if (size.width > 0)
            const_cast<wxSize&>(m_video_size) = {(int) size.width, (int) size.height};
        return {(int) size.width, (int) size.height};
    } else {
        return {0, 0};
    }
}
