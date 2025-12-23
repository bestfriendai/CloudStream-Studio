// frontend/src/components/Player.tsx

import React, { useRef, useState, useEffect, useCallback } from 'react';
import { VideoAsset, Clip } from '../types';
import { Play, Pause, Scissors, Gauge, AlertCircle, GripHorizontal, Wifi } from 'lucide-react';

interface PlayerProps {
  video: VideoAsset | null;
  onAddClip: (clip: Clip) => void;
  autoPlay?: boolean;
  previewTime?: { start: number; end: number } | null;
}

export const Player: React.FC<PlayerProps> = ({ 
  video, 
  onAddClip, 
  autoPlay = false,
  previewTime
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scrubberRef = useRef<HTMLDivElement>(null);
  
  // ✅ Refs to prevent loops
  const isUpdatingTimeRef = useRef(false);
  const lastUpdateTimeRef = useRef(0);
  const lastBufferUpdate = useRef(0);
  const lastNetworkUpdate = useRef(0);
  
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  
  const [bufferProgress, setBufferProgress] = useState(0);
  const [isBuffering, setIsBuffering] = useState(false);
  const [networkSpeed, setNetworkSpeed] = useState<number | null>(null);
  
  const [controlsHeight, setControlsHeight] = useState(192);
  const [isResizing, setIsResizing] = useState(false);
  const resizeStartY = useRef(0);
  const resizeStartHeight = useRef(0);
  
  const [startPoint, setStartPoint] = useState(0);
  const [endPoint, setEndPoint] = useState(0);
  
  const [isDraggingStart, setIsDraggingStart] = useState(false);
  const [isDraggingEnd, setIsDraggingEnd] = useState(false);
  const [isDraggingScrubber, setIsDraggingScrubber] = useState(false);
  const [dragStartPosition, setDragStartPosition] = useState<{ x: number; y: number } | null>(null);

  const roundToPrecision = useCallback((value: number, precision: number = 3): number => {
    const multiplier = Math.pow(10, precision);
    return Math.round(value * multiplier) / multiplier;
  }, []);

  const formatTime = useCallback((t: number): string => {
    if (!isFinite(t)) return '0:00.000';
    
    const mins = Math.floor(t / 60);
    const secs = Math.floor(t % 60);
    const ms = Math.round((t % 1) * 1000);
    
    return `${mins}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
  }, []);

  const parseTimeString = useCallback((timeStr: string): number => {
    try {
      const parts = timeStr.split(':');
      if (parts.length !== 2) return 0;
      
      const mins = parseInt(parts[0]) || 0;
      const secsParts = parts[1].split('.');
      const secs = parseInt(secsParts[0]) || 0;
      const ms = secsParts[1] ? parseInt(secsParts[1].padEnd(3, '0').slice(0, 3)) : 0;
      
      const totalSeconds = mins * 60 + secs + ms / 1000;
      return roundToPrecision(totalSeconds, 3);
    } catch {
      return 0;
    }
  }, [roundToPrecision]);

  // ✅ 監控網路速度 - 優化版本
  useEffect(() => {
    if (!videoRef.current || !video) return;

    const startTime = performance.now();
    let bytesLoaded = 0;
    let isMounted = true;

    const updateNetworkSpeed = () => {
      if (!isMounted || !videoRef.current) return;

      // ✅ 限制更新頻率
      const now = Date.now();
      if (now - lastNetworkUpdate.current < 2000) return;
      lastNetworkUpdate.current = now;

      const videoElement = videoRef.current;
      
      if (videoElement.buffered.length > 0) {
        const bufferedEnd = videoElement.buffered.end(videoElement.buffered.length - 1);
        const estimatedBytes = bufferedEnd * (videoElement.duration > 0 ? (videoElement.videoWidth * videoElement.videoHeight * 0.5) : 1000000);
        
        const elapsedTime = (performance.now() - startTime) / 1000;
        
        if (elapsedTime > 0 && estimatedBytes > bytesLoaded) {
          bytesLoaded = estimatedBytes;
          const speed = (bytesLoaded / elapsedTime) / (1024 * 1024);
          setNetworkSpeed(speed);
        }
      }
    };

    const intervalId = setInterval(updateNetworkSpeed, 3000); // ✅ 降低頻率
    
    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, [video]);

  // ✅ 監控緩衝進度 - 優化版本
  useEffect(() => {
    if (!videoRef.current) return;

    const video = videoRef.current;
    let isMounted = true;

    const handleProgress = () => {
      if (!isMounted || video.buffered.length === 0 || video.duration === 0) return;
      
      // ✅ 限制更新頻率
      const now = Date.now();
      if (now - lastBufferUpdate.current < 500) return;
      lastBufferUpdate.current = now;
      
      const bufferedEnd = video.buffered.end(video.buffered.length - 1);
      const bufferedPercent = (bufferedEnd / video.duration) * 100;
      
      setBufferProgress(bufferedPercent);
    };

    const handleWaiting = () => {
      if (isMounted) setIsBuffering(true);
    };

    const handleCanPlayThrough = () => {
      if (isMounted) setIsBuffering(false);
    };

    const handleStalled = () => {
      if (isMounted) setIsBuffering(true);
    };

    video.addEventListener('progress', handleProgress);
    video.addEventListener('waiting', handleWaiting);
    video.addEventListener('canplaythrough', handleCanPlayThrough);
    video.addEventListener('stalled', handleStalled);

    return () => {
      isMounted = false;
      video.removeEventListener('progress', handleProgress);
      video.removeEventListener('waiting', handleWaiting);
      video.removeEventListener('canplaythrough', handleCanPlayThrough);
      video.removeEventListener('stalled', handleStalled);
    };
  }, []); // ✅ 空依賴，只在 mount 時設置

  // ✅ Reset state when video changes
  useEffect(() => {
    if (!video) return;
    
    console.log('🎬 載入影片:', video.name);
    
    // ✅ 重置所有狀態
    setError(null);
    setIsLoading(true);
    setIsPlaying(false);
    setCurrentTime(0);
    setStartPoint(0);
    setEndPoint(0);
    setPlaybackRate(1);
    setBufferProgress(0);
    setIsBuffering(false);
    setNetworkSpeed(null);
    
    // ✅ 重置 refs
    lastUpdateTimeRef.current = 0;
    lastBufferUpdate.current = 0;
    lastNetworkUpdate.current = 0;
    
    if (videoRef.current) {
      const videoElement = videoRef.current;
      videoElement.preload = 'auto';
      videoElement.currentTime = 0;
      videoElement.playbackRate = 1;
      videoElement.load();
    }
  }, [video]);

  // ✅ 預覽時間點
  useEffect(() => {
    if (!previewTime || !videoRef.current || duration === 0) return;
    
    console.log('🎯 應用預覽時間點:', previewTime);
    
    setStartPoint(previewTime.start);
    setEndPoint(previewTime.end);
    
    videoRef.current.currentTime = previewTime.start;
    
    const playTimeout = setTimeout(() => {
      if (videoRef.current) {
        videoRef.current.play()
          .then(() => setIsPlaying(true))
          .catch(console.error);
      }
    }, 100);
    
    return () => clearTimeout(playTimeout);
  }, [previewTime, duration]);

  // ✅ 當 startPoint 改變時 - 不更新 state
  useEffect(() => {
    if (!videoRef.current || isDraggingStart || isDraggingEnd || isDraggingScrubber) return;
    
    const now = Date.now();
    if (now - lastUpdateTimeRef.current < 100) return;
    lastUpdateTimeRef.current = now;
    
    if (Math.abs(videoRef.current.currentTime - startPoint) > 0.01) {
      videoRef.current.currentTime = startPoint;
      // ✅ 不調用 setCurrentTime，讓 timeupdate 事件自然觸發
    }
  }, [startPoint, isDraggingStart, isDraggingEnd, isDraggingScrubber]);

  // ✅ 監控播放進度
  useEffect(() => {
    if (!videoRef.current || !isPlaying) return;

    const checkPlaybackBounds = () => {
      if (!videoRef.current) return;
      
      const current = videoRef.current.currentTime;
      
      if (current >= endPoint) {
        videoRef.current.pause();
        videoRef.current.currentTime = startPoint;
        setIsPlaying(false);
      }
      
      if (current < startPoint) {
        videoRef.current.currentTime = startPoint;
      }
    };

    const intervalId = setInterval(checkPlaybackBounds, 100);
    return () => clearInterval(intervalId);
  }, [isPlaying, startPoint, endPoint]);

  // ✅ 處理拖曳調整高度
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    resizeStartY.current = e.clientY;
    resizeStartHeight.current = controlsHeight;
  }, [controlsHeight]);

  useEffect(() => {
    if (!isResizing) return;

    const handleResizeMove = (e: MouseEvent) => {
      const deltaY = resizeStartY.current - e.clientY;
      const newHeight = Math.max(150, Math.min(600, resizeStartHeight.current + deltaY));
      setControlsHeight(newHeight);
    };

    const handleResizeEnd = () => {
      setIsResizing(false);
    };

    document.addEventListener('mousemove', handleResizeMove);
    document.addEventListener('mouseup', handleResizeEnd);
    
    return () => {
      document.removeEventListener('mousemove', handleResizeMove);
      document.removeEventListener('mouseup', handleResizeEnd);
    };
  }, [isResizing]);

  // ✅ 處理時間軸標記拖曳
  useEffect(() => {
    if (!isDraggingStart && !isDraggingEnd && !isDraggingScrubber) return;

    let animationFrameId: number;

    const handleMarkerDrag = (e: MouseEvent) => {
      if (!scrubberRef.current) return;
      
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
      
      animationFrameId = requestAnimationFrame(() => {
        if (!scrubberRef.current) return;
        
        const rect = scrubberRef.current.getBoundingClientRect();
        const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
        const percentage = x / rect.width;
        const newTime = roundToPrecision(percentage * duration, 3);
        
        if (isDraggingStart) {
          const newStart = Math.min(newTime, endPoint - 0.001);
          setStartPoint(roundToPrecision(newStart, 3));
          if (videoRef.current) {
            videoRef.current.currentTime = newStart;
          }
        } else if (isDraggingEnd) {
          const newEnd = Math.max(newTime, startPoint + 0.001);
          setEndPoint(roundToPrecision(newEnd, 3));
        } else if (isDraggingScrubber) {
          const clampedTime = Math.max(startPoint, Math.min(newTime, endPoint));
          if (videoRef.current) {
            videoRef.current.currentTime = clampedTime;
          }
        }
      });
    };

    const handleMarkerDragEnd = () => {
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
      
      setIsDraggingStart(false);
      setIsDraggingEnd(false);
      setIsDraggingScrubber(false);
      setDragStartPosition(null);
    };

    document.addEventListener('mousemove', handleMarkerDrag);
    document.addEventListener('mouseup', handleMarkerDragEnd);
    
    return () => {
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
      document.removeEventListener('mousemove', handleMarkerDrag);
      document.removeEventListener('mouseup', handleMarkerDragEnd);
    };
  }, [isDraggingStart, isDraggingEnd, isDraggingScrubber, duration, startPoint, endPoint, roundToPrecision]);

  const togglePlay = useCallback(() => {
    if (!videoRef.current) return;
    
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      const current = videoRef.current.currentTime;
      if (current < startPoint || current >= endPoint) {
        videoRef.current.currentTime = startPoint;
      }
      
      videoRef.current.play()
        .then(() => setIsPlaying(true))
        .catch((err) => {
          console.error('Play error:', err);
          setError('Failed to play video: ' + err.message);
          setIsPlaying(false);
        });
    }
  }, [isPlaying, startPoint, endPoint]);

  // ✅ 優化 timeUpdate 處理
  const handleTimeUpdate = useCallback(() => {
    if (!videoRef.current || isUpdatingTimeRef.current) return;
    
    const newTime = roundToPrecision(videoRef.current.currentTime, 3);
    
    // ✅ 只有當時間真的改變時才更新
    if (Math.abs(newTime - currentTime) < 0.001) return;
    
    isUpdatingTimeRef.current = true;
    
    requestAnimationFrame(() => {
      setCurrentTime(newTime);
      isUpdatingTimeRef.current = false;
    });
  }, [roundToPrecision, currentTime]);

  const handleLoadedMetadata = useCallback(() => {
    console.log('📋 影片 metadata 已載入');
    setIsLoading(false);
    
    if (videoRef.current) {
      const dur = roundToPrecision(videoRef.current.duration, 3);
      setDuration(dur);
      setEndPoint(dur);
      
      console.log(`⏱️ 影片時長: ${formatTime(dur)}`);
      
      if (autoPlay) {
        videoRef.current.play()
          .then(() => setIsPlaying(true))
          .catch(console.error);
      }
    }
  }, [autoPlay, formatTime, roundToPrecision]);

  const handleCanPlay = useCallback(() => {
    console.log('✅ 影片可以播放');
    setIsLoading(false);
    setError(null);
  }, []);

  const handleError = useCallback((e: React.SyntheticEvent<HTMLVideoElement, Event>) => {
    console.error('❌ 影片錯誤:', e);
    setIsLoading(false);
    
    const videoElement = e.currentTarget;
    let errorMessage = 'Failed to load video';
    
    if (videoElement.error) {
      switch (videoElement.error.code) {
        case MediaError.MEDIA_ERR_ABORTED:
          errorMessage = 'Video loading aborted';
          break;
        case MediaError.MEDIA_ERR_NETWORK:
          errorMessage = 'Network error while loading video';
          break;
        case MediaError.MEDIA_ERR_DECODE:
          errorMessage = 'Video decoding failed';
          break;
        case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
          errorMessage = 'Video format not supported or source not found';
          break;
      }
      
      if (videoElement.error.message) {
        errorMessage += ': ' + videoElement.error.message;
      }
    }
    
    setError(errorMessage);
  }, []);

  const handleSpeedChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const rate = parseFloat(e.target.value);
    setPlaybackRate(rate);
    if (videoRef.current) {
      videoRef.current.playbackRate = rate;
    }
  }, []);

  const handleCreateClip = useCallback(() => {
    if (!video) {
      alert('請先選擇影片');
      return;
    }

    if (startPoint >= endPoint) {
      alert('開始時間必須小於結束時間');
      return;
    }

    if (endPoint - startPoint < 0.1) {
      alert('片段時長至少需要 0.1 秒');
      return;
    }

    const newClip: Clip = {
      id: crypto.randomUUID(),
      sourceVideoId: video.id,
      name: `${video.name} (${formatTime(startPoint)}-${formatTime(endPoint)})`,
      startTime: roundToPrecision(startPoint, 3),
      endTime: roundToPrecision(endPoint, 3),
    };
    
    onAddClip(newClip);
    
    console.log(`✅ 剪輯已添加到時間軸`);
  }, [video, startPoint, endPoint, onAddClip, formatTime, roundToPrecision]);

  const handleTimelineClick = useCallback((e: React.MouseEvent) => {
    if (!scrubberRef.current || !videoRef.current || !duration) return;
    
    const rect = scrubberRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = x / rect.width;
    const clickedTime = roundToPrecision(percentage * duration, 3);
    
    const clampedTime = Math.max(startPoint, Math.min(clickedTime, endPoint));
    
    videoRef.current.currentTime = clampedTime;
  }, [duration, startPoint, endPoint, roundToPrecision]);

  if (!video) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black text-gray-500 flex-col min-h-0">
        <div className="w-16 h-16 border-2 border-gray-700 rounded-full flex items-center justify-center mb-4">
          <Play className="w-8 h-8 ml-1" />
        </div>
        <p>Select a video from the bucket to start editing</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="flex-1 flex flex-col bg-black overflow-hidden relative min-h-0">
      {/* Video Area */}
      <div 
        className="flex items-center justify-center relative bg-black group"
        style={{ height: `calc(100% - ${controlsHeight}px)` }}
      >
        <video
          ref={videoRef}
          className="max-h-full max-w-full outline-none"
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onCanPlay={handleCanPlay}
          onError={handleError}
          onEnded={() => {
            setIsPlaying(false);
            if (videoRef.current) {
              videoRef.current.currentTime = startPoint;
            }
          }}
          onClick={togglePlay}
          playsInline
          preload="auto"
          crossOrigin="anonymous"
        >
          <source src={video.url} type="video/mp4" />
          <source src={video.url} type="video/webm" />
          Your browser does not support the video tag.
        </video>
        
        {/* Loading & Buffering */}
        {(isLoading || isBuffering) && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50">
            <div className="flex flex-col items-center gap-3">
              <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
              <p className="text-white text-sm">
                {isLoading ? 'Loading video...' : 'Buffering...'}
              </p>
              {bufferProgress > 0 && bufferProgress < 100 && (
                <>
                  <div className="w-48 bg-gray-700 rounded-full h-2 overflow-hidden">
                    <div 
                      className="bg-blue-500 h-full transition-all duration-300"
                      style={{ width: `${bufferProgress}%` }}
                    ></div>
                  </div>
                  <p className="text-xs text-gray-400">
                    {bufferProgress.toFixed(1)}% buffered
                  </p>
                </>
              )}
            </div>
          </div>
        )}
        
        {/* Error Display */}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/80 p-8">
            <div className="max-w-md bg-red-900/30 border border-red-500 rounded-lg p-6 text-center">
              <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
              <h3 className="text-white text-lg font-semibold mb-2">Video Error</h3>
              <p className="text-red-200 text-sm mb-4">{error}</p>
              <button
                onClick={() => {
                  setError(null);
                  if (videoRef.current) {
                    videoRef.current.load();
                  }
                }}
                className="bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded text-sm"
              >
                Retry
              </button>
            </div>
          </div>
        )}
        
        {/* Play/Pause Overlay */}
        {!error && !isLoading && (
          <div 
            className={`absolute inset-0 flex items-center justify-center bg-black/20 cursor-pointer transition-opacity duration-200 ${
              isPlaying ? 'opacity-0 group-hover:opacity-100' : 'opacity-100'
            }`}
            onClick={togglePlay}
          >
            <div className="w-16 h-16 bg-white/10 backdrop-blur rounded-full flex items-center justify-center hover:scale-105 transition hover:bg-white/20">
              {isPlaying ? (
                <Pause className="w-8 h-8 text-white fill-current" />
              ) : (
                <Play className="w-8 h-8 ml-1 text-white fill-current" />
              )}
            </div>
          </div>
        )}

        {/* Network Speed Indicator */}
        {networkSpeed !== null && networkSpeed > 0 && (
          <div className="absolute top-4 right-4 bg-black/70 backdrop-blur px-3 py-2 rounded-lg flex items-center gap-2 text-xs">
            <Wifi className={`w-4 h-4 ${networkSpeed > 1 ? 'text-green-400' : networkSpeed > 0.5 ? 'text-yellow-400' : 'text-red-400'}`} />
            <span className="text-white font-mono">
              {networkSpeed.toFixed(2)} MB/s
            </span>
          </div>
        )}
      </div>

      {/* Resize Handle */}
      <div
        className={`h-1 bg-[#333] hover:bg-blue-500 cursor-row-resize flex items-center justify-center group transition-colors relative ${
          isResizing ? 'bg-blue-500' : ''
        }`}
        onMouseDown={handleResizeStart}
      >
        <div className="absolute inset-0 flex items-center justify-center">
          <GripHorizontal className="w-5 h-5 text-gray-600 group-hover:text-blue-400 transition-colors" />
        </div>
        <div className="absolute inset-x-0 -top-2 -bottom-2" />
      </div>

      {/* Controls Area */}
      <div 
        className="bg-[#1e1e1e] border-t border-[#333] p-4 flex flex-col gap-4 shrink-0 overflow-y-auto"
        style={{ height: `${controlsHeight}px` }}
      >
        
        {/* Timeline */}
        <div 
          ref={scrubberRef} 
          className="relative h-12 flex items-center shrink-0"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget || (e.target as HTMLElement).classList.contains('timeline-track')) {
              handleTimelineClick(e);
            }
          }}
        >
          {/* Buffer Progress */}
          {bufferProgress > 0 && duration > 0 && (
            <div 
              className="absolute h-2 bg-gray-600/50 rounded"
              style={{
                left: 0,
                width: `${bufferProgress}%`
              }}
            ></div>
          )}

          {/* Timeline Track */}
          <div className="timeline-track absolute left-0 right-0 h-2 bg-[#333] rounded pointer-events-auto"></div>

          {/* Selected Range */}
          {duration > 0 && (
            <div 
              className="absolute h-2 bg-blue-600/60 rounded cursor-pointer pointer-events-auto"
              style={{
                left: `${(startPoint / duration) * 100}%`,
                width: `${((endPoint - startPoint) / duration) * 100}%`
              }}
              onMouseDown={(e) => {
                e.stopPropagation();
                handleTimelineClick(e);
              }}
            ></div>
          )}

          {/* Playhead */}
          {duration > 0 && currentTime >= startPoint && currentTime <= endPoint && (
            <div 
              className={`absolute w-0.5 h-8 bg-white z-20 cursor-ew-resize group/playhead transition-all ${
                isDraggingScrubber ? 'w-1 bg-blue-400' : ''
              }`}
              style={{ 
                left: `${(currentTime / duration) * 100}%`
              }}
              onMouseDown={(e) => {
                e.stopPropagation();
                e.preventDefault();
                
                setDragStartPosition({ x: e.clientX, y: e.clientY });
                setIsDraggingScrubber(true);
                
                if (isPlaying && videoRef.current) {
                  videoRef.current.pause();
                  setIsPlaying(false);
                }
              }}
            >
              <div className={`absolute -top-1 -left-1.5 w-3 h-3 bg-white rotate-45 cursor-ew-resize hover:scale-125 transition-all ${
                isDraggingScrubber ? 'scale-150 bg-blue-400' : ''
              }`}></div>
              
              <div className={`absolute -top-8 left-1/2 -translate-x-1/2 text-[10px] px-2 py-1 rounded whitespace-nowrap pointer-events-none transition-all ${
                isDraggingScrubber 
                  ? 'bg-blue-500 text-white opacity-100 scale-110' 
                  : 'bg-white/90 text-black opacity-0 group-hover/playhead:opacity-100'
              }`}>
                {formatTime(currentTime)}
              </div>
              
              <div className="absolute -left-3 -right-3 -top-2 -bottom-2 cursor-ew-resize"></div>
            </div>
          )}

          {/* Start Marker */}
          {duration > 0 && (
            <div 
              className="absolute w-4 h-8 bg-blue-500 rounded-l cursor-ew-resize z-30 flex items-center justify-center group hover:bg-blue-400 active:bg-blue-600 transition-colors"
              style={{ 
                left: `${(startPoint / duration) * 100}%`,
                transform: 'translateX(-50%)'
              }}
              onMouseDown={(e) => {
                e.stopPropagation();
                e.preventDefault();
                
                setDragStartPosition({ x: e.clientX, y: e.clientY });
                setIsDraggingStart(true);
                
                if (isPlaying && videoRef.current) {
                  videoRef.current.pause();
                  setIsPlaying(false);
                }
              }}
            >
              <div className="w-0.5 h-4 bg-white/50"></div>
              <div className="absolute -top-8 bg-blue-600 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none shadow-lg">
                Start: {formatTime(startPoint)}
              </div>
            </div>
          )}

          {/* End Marker */}
          {duration > 0 && (
            <div 
              className="absolute w-4 h-8 bg-blue-500 rounded-r cursor-ew-resize z-30 flex items-center justify-center group hover:bg-blue-400 active:bg-blue-600 transition-colors"
              style={{ 
                left: `${(endPoint / duration) * 100}%`,
                transform: 'translateX(-50%)'
              }}
              onMouseDown={(e) => {
                e.stopPropagation();
                e.preventDefault();
                setIsDraggingEnd(true);
                if (isPlaying && videoRef.current) {
                  videoRef.current.pause();
                  setIsPlaying(false);
                }
              }}
            >
              <div className="w-0.5 h-4 bg-white/50"></div>
              <div className="absolute -top-8 bg-blue-600 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none shadow-lg">
                End: {formatTime(endPoint)}
              </div>
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="flex justify-between items-start shrink-0 gap-4">
          <div className="flex flex-col gap-3">
            <div className="flex gap-4 items-center">
              <button 
                onClick={togglePlay}
                disabled={!!error || isLoading}
                className="w-10 h-10 rounded-full bg-white text-black flex items-center justify-center hover:bg-gray-200 transition disabled:bg-gray-600 disabled:cursor-not-allowed shrink-0"
              >
                {isPlaying ? <Pause className="w-5 h-5 fill-current" /> : <Play className="w-5 h-5 fill-current ml-0.5" />}
              </button>
              
              <div className="text-sm font-mono text-gray-400 shrink-0">
                {formatTime(currentTime)} <span className="text-gray-600">/</span> {formatTime(duration)}
              </div>

              {bufferProgress > 0 && bufferProgress < 100 && (
                <div className="text-xs text-gray-500 shrink-0">
                  ({bufferProgress.toFixed(0)}% buffered)
                </div>
              )}
            </div>

            <div className="flex gap-4 items-center ml-14">
              <div className="flex items-center gap-2 group relative shrink-0">
                <Gauge className="w-4 h-4 text-gray-500" />
                <input 
                  type="range" 
                  min="0.5" 
                  max="2" 
                  step="0.1" 
                  value={playbackRate}
                  onChange={handleSpeedChange}
                  disabled={!!error || isLoading}
                  className="w-20 h-1 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                />
                <span className="text-xs text-gray-400 font-mono w-8 text-right">{playbackRate.toFixed(1)}x</span>
              </div>

              <div className="text-xs font-mono text-blue-400 bg-blue-900/20 px-2 py-1 rounded border border-blue-500/30 shrink-0">
                Clip: {formatTime(startPoint)} → {formatTime(endPoint)} ({formatTime(endPoint - startPoint)})
              </div>
            </div>
          </div>

          <div className="flex gap-4 items-center bg-[#111] p-2 rounded-lg border border-[#333] shrink-0">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-gray-500 uppercase font-bold tracking-wider">Start</label>
              <input 
                type="text" 
                value={formatTime(startPoint)} 
                onChange={(e) => {
                  const newTime = parseTimeString(e.target.value);
                  setStartPoint(Math.min(newTime, endPoint - 0.001));
                }}
                placeholder="0:00.000"
                disabled={!duration}
                className="w-24 bg-[#222] border border-[#444] text-white text-xs p-1 rounded focus:border-blue-500 outline-none disabled:opacity-50 text-center font-mono"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-gray-500 uppercase font-bold tracking-wider">End</label>
              <input 
                type="text" 
                value={formatTime(endPoint)} 
                onChange={(e) => {
                  const newTime = parseTimeString(e.target.value);
                  setEndPoint(Math.max(newTime, startPoint + 0.001));
                }}
                placeholder="0:00.000"
                disabled={!duration}
                className="w-24 bg-[#222] border border-[#444] text-white text-xs p-1 rounded focus:border-blue-500 outline-none disabled:opacity-50 text-center font-mono"
              />
            </div>
            <div className="h-8 w-px bg-[#333] mx-2"></div>
            <button 
              onClick={handleCreateClip}
              disabled={!duration || startPoint >= endPoint}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm font-medium transition disabled:bg-gray-600 disabled:cursor-not-allowed"
            >
              <Scissors className="w-4 h-4" />
              Clip & Add
            </button>
          </div>
        </div>

        <div className="text-[10px] text-gray-600 text-center shrink-0">
          Controls Height: {controlsHeight}px (Drag the line above to resize)
        </div>
      </div>
    </div>
  );
};