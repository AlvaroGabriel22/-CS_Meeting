import { Navigate, Route, Routes } from 'react-router-dom'

import { Topbar } from '@/components/layout/Topbar'
import { Department } from '@/pages/Department'
import { Home } from '@/pages/Home'
import { Settings } from '@/pages/Settings'

export default function App() {
  return (
    <div className="min-h-screen">
      <Topbar />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/department/:code" element={<Department />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
