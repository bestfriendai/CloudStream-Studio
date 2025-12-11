// vite.config.ts
import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';

export default defineConfig(({ command, mode }) => {
    // 自定義環境文件載入
    // Vite 默認使用 .env.development 和 .env.production
    // 我們改為使用 .env.dev 和 .env.prod
    
    let customEnv: Record<string, string> = {};
    
    // 根據 mode 載入對應的環境文件
    const envFile = mode === 'production' ? '.env.prod' : '.env.dev';
    const envPath = path.resolve(process.cwd(), envFile);
    
    console.log('======================');
    console.log('Vite Configuration');
    console.log('======================');
    console.log('Command:', command);
    console.log('Mode:', mode);
    console.log('Looking for env file:', envFile);
    
    // 手動讀取環境文件
    if (fs.existsSync(envPath)) {
        console.log('✓ Found:', envPath);
        const envContent = fs.readFileSync(envPath, 'utf-8');
        
        // 解析環境變數
        envContent.split('\n').forEach(line => {
            line = line.trim();
            if (line && !line.startsWith('#')) {
                const [key, ...valueParts] = line.split('=');
                if (key && valueParts.length > 0) {
                    const value = valueParts.join('=').trim();
                    customEnv[key] = value;
                }
            }
        });
        
        console.log('Loaded variables:', Object.keys(customEnv));
    } else {
        console.log('✗ Not found:', envPath);
    }
    
    // 也載入 Vite 默認的環境變數（作為後備）
    const viteEnv = loadEnv(mode, process.cwd(), '');
    
    // 合併環境變數（自定義的優先）
    const env = { ...viteEnv, ...customEnv };
    
    // 獲取 API Base URL
    const apiBaseUrl = env.VITE_API_BASE_URL || 'http://localhost:8000/api';
    
    console.log('VITE_API_BASE_URL:', apiBaseUrl);
    console.log('======================');

    return {
      server: {
        port: 3000,
        host: '0.0.0.0',
        proxy: {
          '/api': {
            target: apiBaseUrl.replace('/api', ''),
            changeOrigin: true,
            rewrite: (path) => path,
          }
        }
      },
      plugins: [react()],
      define: {
        // 在構建時替換這個值
        'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiBaseUrl),
      },
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      },
      build: {
        outDir: 'dist',
        sourcemap: mode === 'development',
        minify: mode === 'production' ? 'esbuild' : false,
        rollupOptions: {
          output: {
            manualChunks: {
              vendor: ['react', 'react-dom'],
            },
          },
        },
      },
      envPrefix: 'VITE_',
    };
});
