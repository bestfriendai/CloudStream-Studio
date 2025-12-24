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
  
  const isDraggingRef = useRef(false);
  const currentTimeRef = useRef(0);
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
  
  const [dragType, setDragType] = useState<'start' | 'end' | 'scrubber' | null>(null);

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

  // ✅ 監控網路速度
  useEffect(() => {
    if (!videoRef.current || !video) return;

    const startTime = performance.now();
    let bytesLoaded = 0;
    let isMounted = true;

    const updateNetworkSpeed = () => {
      if (!isMounted || !videoRef.current) return;

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

    const intervalId = setInterval(updateNetworkSpeed, 3000);
    
    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, [video]);

  // ✅ 監控緩衝進度
  useEffect(() => {
    if (!videoRef.current) return;

    const videoEl = videoRef.current;
    let isMounted = true;

    const handleProgress = () => {
      if (!isMounted || videoEl.buffered.length === 0 || videoEl.duration === 0) return;
      
      const now = Date.now();
      if (now - lastBufferUpdate.current < 500) return;
      lastBufferUpdate.current = now;
      
      const bufferedEnd = videoEl.buffered.end(videoEl.buffered.length - 1);
      const bufferedPercent = (bufferedEnd / videoEl.duration) * 100;
      
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

    videoEl.addEventListener('progress', handleProgress);
    videoEl.addEventListener('waiting', handleWaiting);
    videoEl.addEventListener('canplaythrough', handleCanPlayThrough);
    videoEl.addEventListener('stalled', handleStalled);

    return () => {
      isMounted = false;
      videoEl.removeEventListener('progress', handleProgress);
      videoEl.removeEventListener('waiting', handleWaiting);
      videoEl.removeEventListener('canplaythrough', handleCanPlayThrough);
      videoEl.removeEventListener('stalled', handleStalled);
    };
  }, []);

  // ✅ Reset state when video changes
  useEffect(() => {
    if (!video) return;
    
    console.log('🎬 載入影片:', video.name, 'URL:', video.url);
    
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
    setDragType(null);
    
    currentTimeRef.current = 0;
    isDraggingRef.current = false;
    
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
    currentTimeRef.current = previewTime.start;
    setCurrentTime(previewTime.start);
    
    const playTimeout = setTimeout(() => {
      if (videoRef.current) {
        videoRef.current.play()
          .then(() => setIsPlaying(true))
          .catch(console.error);
      }
    }, 100);
    
    return () => clearTimeout(playTimeout);
  }, [previewTime, duration]);

  // ✅ 監控播放進度
  useEffect(() => {
    if (!videoRef.current || !isPlaying) return;

    const checkPlaybackBounds = () => {
      if (!videoRef.current || isDraggingRef.current) return;
      
      const current = videoRef.current.currentTime;
      
      if (current >= endPoint) {
        videoRef.current.pause();
        videoRef.current.currentTime = startPoint;
        currentTimeRef.current = startPoint;
        setCurrentTime(startPoint);
        setIsPlaying(false);
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

  // ✅ 統一的拖曳處理
  useEffect(() => {
    if (!dragType) {
      isDraggingRef.current = false;
      return;
    }

    isDraggingRef.current = true;
    console.log('🎯 開始拖曳:', dragType);

    const handleMouseMove = (e: MouseEvent) => {
      if (!scrubberRef.current || !videoRef.current) return;
      
      const rect = scrubberRef.current.getBoundingClientRect();
      const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
      const percentage = x / rect.width;
      const newTime = roundToPrecision(percentage * duration, 3);
      
      if (dragType === 'start') {
        const clampedStart = Math.max(0, Math.min(newTime, endPoint - 0.1));
        setStartPoint(clampedStart);
        videoRef.current.currentTime = clampedStart;
        currentTimeRef.current = clampedStart;
        setCurrentTime(clampedStart);
      } else if (dragType === 'end') {
        const clampedEnd = Math.max(startPoint + 0.1, Math.min(newTime, duration));
        setEndPoint(clampedEnd);
      } else if (dragType === 'scrubber') {
        const clampedTime = Math.max(startPoint, Math.min(newTime, endPoint));
        videoRef.current.currentTime = clampedTime;
        currentTimeRef.current = clampedTime;
        setCurrentTime(clampedTime);
      }
    };

    const handleMouseUp = () => {
      console.log('🎯 結束拖曳');
      setDragType(null);
      isDraggingRef.current = false;
    };

    document.addEventListener('mousemove', handleMouseMove, { passive: false });
    document.addEventListener('mouseup', handleMouseUp);
    
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [dragType, duration, startPoint, endPoint, roundToPrecision]);

  const togglePlay = useCallback(() => {
    if (!videoRef.current) return;
    
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      const current = videoRef.current.currentTime;
      if (current < startPoint || current >= endPoint) {
        videoRef.current.currentTime = startPoint;
        currentTimeRef.current = startPoint;
        setCurrentTime(startPoint);
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

  const handleTimeUpdate = useCallback(() => {
    if (!videoRef.current || isDraggingRef.current) return;
    
    const newTime = roundToPrecision(videoRef.current.currentTime, 3);
    
    if (Math.abs(newTime - currentTimeRef.current) < 0.05) return;
    
    currentTimeRef.current = newTime;
    setCurrentTime(newTime);
  }, [roundToPrecision]);

  const handleLoadedMetadata = useCallback(() => {
    console.log('📋 影片 metadata 已載入');
    setIsLoading(false);
    setError(null); // ✅ 清除之前的錯誤
    
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

  // ✅ 修復：正確處理 video 元素的錯誤
  const handleVideoError = useCallback(() => {
    // 直接從 videoRef 獲取錯誤資訊
    const videoElement = videoRef.current;
    
    if (!videoElement) {
      console.error('❌ 影片錯誤: videoRef 為空');
      return;
    }
    
    console.error('❌ 影片錯誤:', {
      error: videoElement.error,
      networkState: videoElement.networkState,
      readyState: videoElement.readyState,
      src: video?.url
    });
    
    setIsLoading(false);
    
    let errorMessage = 'Failed to load video';
    
    if (videoElement.error) {
      switch (videoElement.error.code) {
        case MediaError.MEDIA_ERR_ABORTED:
          errorMessage = 'Video loading was aborted';
          break;
        case MediaError.MEDIA_ERR_NETWORK:
          errorMessage = 'Network error while loading video. Please check your connection.';
          break;
        case MediaError.MEDIA_ERR_DECODE:
          errorMessage = 'Video decoding failed. The file may be corrupted.';
          break;
        case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
          errorMessage = 'Video format not supported or source not found';
          break;
        default:
          errorMessage = `Unknown error (code: ${videoElement.error.code})`;
      }
      
      if (videoElement.error.message) {
        errorMessage += `: ${videoElement.error.message}`;
      }
    } else {
      // 沒有 error 對象時，檢查網路狀態
      switch (videoElement.networkState) {
        case HTMLMediaElement.NETWORK_EMPTY:
          errorMessage = 'Video not initialized';
          break;
        case HTMLMediaElement.NETWORK_IDLE:
          errorMessage = 'Video source not found';
          break;
        case HTMLMediaElement.NETWORK_LOADING:
          errorMessage = 'Video is still loading...';
          // 可能只是暫時的，不設置錯誤
          return;
        case HTMLMediaElement.NETWORK_NO_SOURCE:
          errorMessage = 'No video source available';
          break;
      }
    }
    
    // 添加 URL 資訊以便調試
    if (video?.url) {
      console.error('影片 URL:', video.url);
    }
    
    setError(errorMessage);
  }, [video?.url]);

  // ✅ 處理 source 元素錯誤（不觸發主要錯誤狀態）
  const handleSourceError = useCallback((e: React.SyntheticEvent<HTMLSourceElement>) => {
    console.warn('⚠️ Source 載入失敗:', e.currentTarget.src);
    // 不立即設置錯誤，等待所有 source 都失敗後由 video 的 error 事件處理
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
    if (dragType) return;
    
    const rect = scrubberRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = x / rect.width;
    const clickedTime = roundToPrecision(percentage * duration, 3);
    
    const clampedTime = Math.max(startPoint, Math.min(clickedTime, endPoint));
    
    videoRef.current.currentTime = clampedTime;
    currentTimeRef.current = clampedTime;
    setCurrentTime(clampedTime);
  }, [duration, startPoint, endPoint, roundToPrecision, dragType]);

  const handleStartDrag = useCallback((type: 'start' | 'end' | 'scrubber') => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (isPlaying && videoRef.current) {
      videoRef.current.pause();
      setIsPlaying(false);
    }
    
    setDragType(type);
  }, [isPlaying]);

  // ✅ 重試載入影片
  const handleRetry = useCallback(() => {
    setError(null);
    setIsLoading(true);
    
    if (videoRef.current && video) {
      console.log('🔄 重試載入影片:', video.url);
      videoRef.current.load();
    }
  }, [video]);

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
        {/* ✅ 修復：使用 onError 在 video 元素上，而不是 source */}
        <video
          ref={videoRef}
          className="max-h-full max-w-full outline-none"
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onCanPlay={handleCanPlay}
          onError={handleVideoError}
          onEnded={() => {
            setIsPlaying(false);
            if (videoRef.current) {
              videoRef.current.currentTime = startPoint;
              currentTimeRef.current = startPoint;
              setCurrentTime(startPoint);
            }
          }}
          onClick={togglePlay}
          playsInline
          preload="auto"
          crossOrigin="anonymous"
        >
          {/* ✅ 只使用一個 source，根據 content type 決定 */}
          <source 
            src={video.url} 
            type={video.contentType || 'video/mp4'} 
            onError={handleSourceError}
          />
          Your browser does not support the video tag.
        </video>
        
        {/* Loading & Buffering */}
        {(isLoading || isBuffering) && !error && (
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
              
              {/* ✅ 顯示影片 URL 以便調試 */}
              <p className="text-gray-500 text-xs mb-4 break-all">
                URL: {video.url}
              </p>
              
              <div className="flex gap-2 justify-center">
                <button
                  onClick={handleRetry}
                  className="bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded text-sm"
                >
                  Retry
                </button>
                <button
                  onClick={() => setError(null)}
                  className="bg-gray-600 hover:bg-gray-500 text-white px-4 py-2 rounded text-sm"
                >
                  Dismiss
                </button>
              </div>
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
          className="relative h-12 flex items-center shrink-0 cursor-pointer"
          onClick={handleTimelineClick}
        >
          {/* Buffer Progress */}
          {bufferProgress > 0 && duration > 0 && (
            <div 
              className="absolute h-2 bg-gray-600/50 rounded pointer-events-none"
              style={{
                left: 0,
                width: `${bufferProgress}%`
              }}
            ></div>
          )}

          {/* Timeline Track */}
          <div className="absolute left-0 right-0 h-2 bg-[#333] rounded pointer-events-none"></div>

          {/* Selected Range */}
          {duration > 0 && (
            <div 
              className="absolute h-2 bg-blue-600/60 rounded pointer-events-none"
              style={{
                left: `${(startPoint / duration) * 100}%`,
                width: `${((endPoint - startPoint) / duration) * 100}%`
              }}
            ></div>
          )}

          {/* Playhead */}
          {duration > 0 && currentTime >= startPoint && currentTime <= endPoint && (
            <div 
              className={`absolute w-0.5 h-8 bg-white z-20 cursor-ew-resize group/playhead transition-all ${
                dragType === 'scrubber' ? 'w-1 bg-blue-400' : ''
              }`}
              style={{ 
                left: `${(currentTime / duration) * 100}%`,
                transform: 'translateX(-50%)'
              }}
              onMouseDown={handleStartDrag('scrubber')}
            >
              <div className={`absolute -top-1 -left-1.5 w-3 h-3 bg-white rotate-45 cursor-ew-resize hover:scale-125 transition-all ${
                dragType === 'scrubber' ? 'scale-150 bg-blue-400' : ''
              }`}></div>
              
              <div className={`absolute -top-8 left-1/2 -translate-x-1/2 text-[10px] px-2 py-1 rounded whitespace-nowrap pointer-events-none transition-all ${
                dragType === 'scrubber' 
                  ? 'bg-blue-500 text-white opacity-100 scale-110' 
                  : 'bg-white/90 text-black opacity-0 group-hover/playhead:opacity-100'
              }`}>
                {formatTime(currentTime)}
              </div>
              
              <div className="absolute -left-4 -right-4 -top-4 -bottom-4 cursor-ew-resize"></div>
            </div>
          )}

          {/* Start Marker */}
          {duration > 0 && (
            <div 
              className="absolute w-4 h-8 bg-blue-500 rounded-l cursor-ew-resize z-30 flex items-center justify-center group/start hover:bg-blue-400 active:bg-blue-600 transition-colors"
              style={{ 
                left: `${(startPoint / duration) * 100}%`,
                transform: 'translateX(-50%)'
              }}
              onMouseDown={handleStartDrag('start')}
            >
              <div className="w-0.5 h-4 bg-white/50"></div>
              <div className="absolute -top-8 bg-blue-600 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover/start:opacity-100 whitespace-nowrap pointer-events-none shadow-lg">
                Start: {formatTime(startPoint)}
              </div>
              <div className="absolute -left-2 -right-2 -top-2 -bottom-2 cursor-ew-resize"></div>
            </div>
          )}

          {/* End Marker */}
          {duration > 0 && (
            <div 
              className="absolute w-4 h-8 bg-blue-500 rounded-r cursor-ew-resize z-30 flex items-center justify-center group/end hover:bg-blue-400 active:bg-blue-600 transition-colors"
              style={{ 
                left: `${(endPoint / duration) * 100}%`,
                transform: 'translateX(-50%)'
              }}
              onMouseDown={handleStartDrag('end')}
            >
              <div className="w-0.5 h-4 bg-white/50"></div>
              <div className="absolute -top-8 bg-blue-600 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover/end:opacity-100 whitespace-nowrap pointer-events-none shadow-lg">
                End: {formatTime(endPoint)}
              </div>
              <div className="absolute -left-2 -right-2 -top-2 -bottom-2 cursor-ew-resize"></div>
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
              
              {dragType && (
                <div className="text-xs text-blue-400 bg-blue-900/30 px-2 py-1 rounded">
                  拖曳中: {dragType === 'start' ? '起點' : dragType === 'end' ? '終點' : '播放針'}
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
                  const clampedTime = Math.min(newTime, endPoint - 0.1);
                  setStartPoint(clampedTime);
                  if (videoRef.current) {
                    videoRef.current.currentTime = clampedTime;
                    currentTimeRef.current = clampedTime;
                    setCurrentTime(clampedTime);
                  }
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
                  setEndPoint(Math.max(newTime, startPoint + 0.1));
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
