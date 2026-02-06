import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'CDC Monitor - PostgreSQL to Snowflake',
  description: 'Change Data Capture pipeline management console',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
