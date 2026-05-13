import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './store/AuthContext.jsx'
import Navbar      from './components/Navbar.jsx'
import AlertBanner from './components/AlertBanner.jsx'
import Landing     from './pages/Landing.jsx'
import Login       from './pages/Login.jsx'
import Dashboard   from './pages/Dashboard.jsx'
import Loops       from './pages/Loops.jsx'
import Chat        from './pages/Chat.jsx'
import Logs        from './pages/Logs.jsx'

function Guard({ children }) {
  const { user } = useAuth()
  return user ? children : <Navigate to="/login" replace />
}

function Shell({ children }) {
  return (
    <>
      <Navbar />
      <AlertBanner />
      <div className="pt-14">{children}</div>
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
