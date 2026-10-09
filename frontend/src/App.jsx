import { useState } from 'react'
import './App.css'
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import Layout from './components/Layout';
import AboutUs from './components/layouts/AboutUs';
import Chat from './components/layouts/Chat';

function App() {
  const [count, setCount] = useState(0)

  const router = createBrowserRouter([
    {
      element: <Layout />,
      children:[
        {
          path: '/',
          element: <Chat />
        },
        {
          path:'/about',
          element: <AboutUs />
        }
      
      ]
    }
  ])

  return (
    <>
      <RouterProvider router={router} />
    </>
  )
}

export default App
