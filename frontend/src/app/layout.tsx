import type { Metadata } from 'next';
import './globals.css';
import Sidebar from '@/components/layout/Sidebar';

export const metadata: Metadata = {
  title: 'ASTRA — Systems Engineering Platform',
  description: 'Requirements tracking, traceability, and systems engineering management.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Sidebar />
        <main className="ml-60 min-h-screen p-6 lg:p-8">
          {children}
        </main>
      </body>
    </html>
  );
}
