import { useEffect } from 'react'
import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import { useAuthStore } from './store/authStore'
import { ConfirmHost } from './components/common/ConfirmHost'
import { Toasts } from './components/common/Toasts'
import { Spinner } from './components/ui'

export default function App() {
  const { isInitializing, initialize } = useAuthStore()

  useEffect(() => {
    initialize()
  }, [initialize])

  if (isInitializing) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50 text-brand-navy">
        <Spinner size={24} />
      </div>
    )
  }

  return (
    <>
      <RouterProvider router={router} />
      <ConfirmHost />
      <Toasts />
    </>
  )
}
