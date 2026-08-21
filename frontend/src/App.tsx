import { Navigate, Route, Routes } from 'react-router-dom'

import { Topbar } from '@/components/layout/Topbar'
import { Department } from '@/pages/Department'
import { DepartmentConfig } from '@/pages/DepartmentConfig'
import { Home } from '@/pages/Home'
import { Reports } from '@/pages/Reports'
import { Settings } from '@/pages/Settings'

export default function App() {
  return (
    <div className="min-h-screen">
      <Topbar />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/department/:code" element={<Department />} />
          <Route path="/department/:code/config" element={<DepartmentConfig />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
