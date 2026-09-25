import '@xyflow/react/dist/style.css';
import './globals.css';
import './topology-builder.css';
import type { Metadata } from 'next';

export const metadata: Metadata = { title: 'NetPulse | Network performance lab', description: 'Interactive protocol performance analysis' };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
