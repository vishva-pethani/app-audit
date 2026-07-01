import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'App Tag Auditor - Dashboard',
  description: 'Automated Firebase Analytics APK Auditing System',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
