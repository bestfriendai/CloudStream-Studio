// services/api.ts

// API_BASE
export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// 定義後端回傳的檔案格式
export interface GCSFile {
  name: string;
  size: number;
  content_type: string;
  created: string | null;
  updated: string | null;
}

// 縮圖選項
export interface ThumbnailOptions {
  width?: number;
  height?: number;
  time?: number;
  regenerate?: boolean;
}

// 修正：正確編碼 URL
export const getStreamUrl = (filename: string) => {
  const encodedPath = filename.split('/').map(encodeURIComponent).join('/');
  return `${API_BASE}/api/stream/${encodedPath}`;
};

// 新增：取得縮圖 URL
export const getThumbnailUrl = (
  filename: string,
  options: ThumbnailOptions = {}
): string => {
  const encodedPath = filename.split('/').map(encodeURIComponent).join('/');
  const params = new URLSearchParams();
  
  if (options.width) params.append('width', options.width.toString());
  if (options.height) params.append('height', options.height.toString());
  if (options.time !== undefined) params.append('time', options.time.toString());
  if (options.regenerate) params.append('regenerate', 'true');
  
  const queryString = params.toString();
  return `${API_BASE}/api/thumbnail/${encodedPath}${queryString ? '?' + queryString : ''}`;
};

// 新增：取得縮圖（返回 Blob URL）
export const fetchThumbnail = async (
  filename: string,
  options: ThumbnailOptions = {}
): Promise<string> => {
  try {
    const url = getThumbnailUrl(filename, options);
    const response = await fetch(url);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch thumbnail: ${response.statusText}`);
    }
    
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    
    // 記錄來源（新產生 or 快取）
    const source = response.headers.get('X-Thumbnail-Source');
    console.log(`縮圖來源 (${filename}): ${source}`);
    
    return blobUrl;
  } catch (error) {
    console.error('取得縮圖失敗:', error);
    throw error;
  }
};

// 新增：刪除縮圖快取
export const deleteThumbnail = async (
  filename: string,
  width?: number,
  height?: number
): Promise<void> => {
  const encodedPath = filename.split('/').map(encodeURIComponent).join('/');
  const params = new URLSearchParams();
  
  if (width) params.append('width', width.toString());
  if (height) params.append('height', height.toString());
  
  const queryString = params.toString();
  const url = `${API_BASE}/api/thumbnail/${encodedPath}${queryString ? '?' + queryString : ''}`;
  
  const response = await fetch(url, { method: 'DELETE' });
  
  if (!response.ok) {
    throw new Error('Failed to delete thumbnail');
  }
};

// 修正：返回完整的檔案物件
export const fetchFiles = async (): Promise<GCSFile[]> => {
  try {
    const res = await fetch(`${API_BASE}/api/files`);
    if (!res.ok) throw new Error('Failed to fetch files');
    
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (error) {
    console.error("API Error fetching files:", error);
    return [];
  }
};

export const uploadFile = async (file: File): Promise<void> => {
  const formData = new FormData();
  formData.append('file', file);
  
  const res = await fetch(`${API_BASE}/api/upload`, {
    method: 'POST',
    body: formData,
  });
  
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed: ${text}`);
  }
};

export const deleteFile = async (filename: string): Promise<void> => {
  const encodedPath = filename.split('/').map(encodeURIComponent).join('/');
  const res = await fetch(`${API_BASE}/api/files/${encodedPath}`, {
    method: 'DELETE',
  });
  
  if (!res.ok) {
    throw new Error('Delete failed');
  }
};
