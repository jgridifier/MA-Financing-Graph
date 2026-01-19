import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'M&A Financing Graph',
  description: 'SEC EDGAR M&A Deal and Financing Analysis',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>
          <div className="min-h-screen bg-gray-50">
            <nav className="bg-white shadow-sm border-b">
              <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex justify-between h-16">
                  <div className="flex items-center">
                    <a href="/" className="text-xl font-bold text-gray-900">
                      M&A Financing Graph
                    </a>
                    <div className="ml-10 flex items-baseline space-x-4">
                      <a href="/deals" className="text-gray-600 hover:text-gray-900 px-3 py-2">
                        Deals
                      </a>
                      <a href="/filings" className="text-gray-600 hover:text-gray-900 px-3 py-2">
                        Filings
                      </a>
                      <a href="/alerts" className="text-gray-600 hover:text-gray-900 px-3 py-2">
                        Alerts
                      </a>
                    </div>
                  </div>
                </div>
              </div>
            </nav>
            <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  )
}
