import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './store/AuthContext.jsx'
import Navbar      from './components/Navbar.jsx'
import AlertBanner from './components/AlertBanner.jsx'
import Landing     from './pages/Landing.jsx'
import Login       from './pages/Login.jsx'

const Dashboard = lazy(() => import('./pages/Dashboard.jsx'))
const Loops     = lazy(() => import('./pages/Loops.jsx'))
const Chat      = lazy(() => import('./pages/Chat.jsx'))
const Logs      = lazy(() => import('./pages/Logs.jsx'))

function Guard({ children }) {
  const { user } = useAuth()
  return user ? children : <Navigate to="/login" replace />
}

function Shell({ children }) {
  return (
    <>
      <Navbar />
      <AlertBanner />
      <div className="pt-14">
        <Suspense fallback={null}>{children}</Suspense>
      </div>
    </>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/"          element={<Landing />} />
      <Route path="/login"     element={<Login />} />
      <Route path="/dashboard" element={<Guard><Shell><Dashboard /></Shell></Guard>} />
      <Route path="/loops"     element={<Guard><Shell><Loops /></Shell></Guard>} />
      <Route path="/chat"      element={<Guard><Shell><Chat /></Shell></Guard>} />
      <Route path="/logs"      element={<Guard><Shell><Logs /></Shell></Guard>} />
      <Route path="*"          element={<Navigate to="/" />} />
    </Routes>
  )
}
