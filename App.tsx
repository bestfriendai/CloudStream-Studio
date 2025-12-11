import React, { useState, useEffect } from 'react';
import { VideoLibrary } from './components/VideoLibrary';
import { Player } from './components/Player';
import { Timeline } from './components/Timeline';
import { VideoAsset, Clip } from './types';
import { Video as VideoIcon, Download } from 'lucide-react';
import { fetchFiles, uploadFile, deleteFile, getStreamUrl, GCSFile } from './services/api';

const App: React.FC = () => {
  const [videos, setVideos] = useState<VideoAsset[]>([]);
  const [currentVideo, setCurrentVideo] = useState<VideoAsset | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [isSynthesizing, setIsSynthesizing] = useState(false);
  const [isLoadingBucket, setIsLoadingBucket] = useState(true);
  const [isUploading, setIsUploading] = useState(false);

  const convertToVideoAsset = (file: GCSFile, index: number): VideoAsset => {
    const displayName = file.name.split('/').pop() || file.name;
    const streamUrl = getStreamUrl(file.name);
    
    return {
      id: `${file.name}-${index}`,
      name: displayName,
      url: streamUrl,
      duration: 0,
      source: 'bucket' as const,
      fullPath: file.name,
      size: file.size,
      contentType: file.content_type,
      thumbnail: undefined
    };
  };

  const loadFiles = async () => {
    setIsLoadingBucket(true);
    try {
      const files = await fetchFiles();
      
      const videoFiles = files.filter(file => 
        file.content_type && file.content_type.startsWith('video/')
      );
      
      const assets: VideoAsset[] = videoFiles.map((file, index) => 
        convertToVideoAsset(file, index)
      );
      
      setVideos(assets);
    } catch (err) {
      console.error("Failed to load files", err);
      setVideos([]);
    } finally {
      setIsLoadingBucket(false);
    }
  };

  useEffect(() => {
    loadFiles();
  }, []);

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    try {
      await uploadFile(file);
      await loadFiles();
      alert('Upload successful!');
    } catch (err) {
      alert("Upload failed. Check console for details.");
      console.error(err);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (video: VideoAsset) => {
    try {
      const pathToDelete = (video as any).fullPath || video.name;
      await deleteFile(pathToDelete);
      
      if (currentVideo?.id === video.id) {
        setCurrentVideo(null);
      }
      
      setClips(prev => prev.filter(c => c.sourceVideoId !== video.id));
      
      await loadFiles();
      alert('Delete successful!');
    } catch (err) {
      alert("Delete failed.");
      console.error(err);
    }
  };

  const handleDownloadVideo = async () => {
    if (!currentVideo) {
      alert('Please select a video first!');
      return;
    }

    try {
      // 直接使用 stream URL 下載
      const link = document.createElement('a');
      link.href = currentVideo.url;
      link.download = currentVideo.name;
      link.target = '_blank';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      console.log('Downloading:', currentVideo.name);
    } catch (err) {
      console.error('Download failed:', err);
      alert('Download failed. Please try again.');
    }
  };

  const handleAddClip = (clip: Clip) => {
    setClips(prev => [...prev, clip]);
  };

  const handleRemoveClip = (clipId: string) => {
    setClips(prev => prev.filter(c => c.id !== clipId));
  };

  const handleSynthesize = () => {
    if (clips.length === 0) {
      alert('No clips to synthesize!');
      return;
    }
    
    setIsSynthesizing(true);
    setTimeout(() => {
      setIsSynthesizing(false);
      alert(`Synthesis Complete! \n\nMerged ${clips.length} clips.\nOutput would be downloaded from backend.`);
    }, 2000);
  };

  const assetMap = React.useMemo(() => {
    const map: Record<string, VideoAsset> = {};
    videos.forEach(v => map[v.id] = v);
    return map;
  }, [videos]);

  return (
    <div className="flex flex-col h-screen bg-[#0f0f0f] text-white overflow-hidden">
      {/* Top Bar */}
      <header className="h-14 border-b border-[#333] bg-[#1a1a1a] flex items-center px-4 justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-purple-600 rounded flex items-center justify-center shadow-lg">
             <VideoIcon className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-lg font-bold tracking-tight">
            CloudStream <span className="text-blue-400 font-light">Manager</span>
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-xs text-gray-500 bg-[#222] px-3 py-1 rounded-full border border-[#333]">
            Backend: Connected (localhost:8000)
          </div>
          <div className="text-xs text-gray-400 bg-[#222] px-3 py-1 rounded-full border border-[#333]">
            {videos.length} video{videos.length !== 1 ? 's' : ''}
          </div>
          <div className="text-xs text-gray-400 bg-[#222] px-3 py-1 rounded-full border border-[#333]">
            {clips.length} clip{clips.length !== 1 ? 's' : ''}
          </div>
          
          {/* Download Current Video 按鈕 */}
          <button 
            className={`flex items-center gap-2 px-4 py-1.5 rounded text-sm transition ${
              currentVideo 
                ? 'bg-blue-600 hover:bg-blue-500 text-white' 
                : 'bg-[#333] text-gray-500 cursor-not-allowed'
            }`}
            onClick={handleDownloadVideo}
            disabled={!currentVideo}
            title={currentVideo ? `Download ${currentVideo.name}` : 'No video selected'}
          >
            <Download className="w-4 h-4" />
            Download Video
          </button>
        </div>
      </header>

      {/* Main Workspace */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Left: Bucket / Library */}
        <VideoLibrary 
          videos={videos} 
          onSelectVideo={setCurrentVideo} 
          onUpload={handleUpload}
          onDelete={handleDelete}
          isLoading={isLoadingBucket}
          isUploading={isUploading}
        />

        {/* Right: Player & Timeline */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <div className="flex-1 min-h-0 flex flex-col">
            <Player 
              video={currentVideo} 
              onAddClip={handleAddClip} 
            />
          </div>
          
          <Timeline 
            clips={clips} 
            assets={assetMap}
            onRemoveClip={handleRemoveClip}
            onSynthesize={handleSynthesize}
            isSynthesizing={isSynthesizing}
          />
        </div>
      </div>
    </div>
  );
};

export default App;
