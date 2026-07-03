import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  output: 'export',
  images: {
    unoptimized: true,
  },
  // trailingSlash must be FALSE for Electron's app:// protocol.
  // With trailingSlash:true, scripts load from app://index.html/_next/...
  // instead of app://_next/..., breaking hydration entirely.
  trailingSlash: false,
};

export default nextConfig;
