import { useState } from 'react'
import { Layout } from './components/Layout'
import { Toast } from './components/Toast'
import { HomePage } from './pages/Home'
import { ImagePage } from './pages/Image'
import { Img2ImgPage } from './pages/Img2Img'
import { VideoPage } from './pages/Video'
import { VideoTasksPage } from './pages/VideoTasks'
import { DramaPage } from './pages/Drama'
import { DramaFlowPage } from './pages/DramaFlow'
import { AnchorPage } from './pages/Anchor'
import { FilesPage } from './pages/Files'
import { Settings } from './pages/Settings'

export default function App() {
  const [activeTab, setActiveTab] = useState('home')
  const [showSettings, setShowSettings] = useState(false)

  const renderPage = () => {
    switch (activeTab) {
      case 'home': return <HomePage />
      case 'image': return <ImagePage />
      case 'img2img': return <Img2ImgPage />
      case 'video': return <VideoPage />
      case 'videoTasks': return <VideoTasksPage />
      case 'drama': return <DramaPage />
      case 'dramaFlow': return <DramaFlowPage />
      case 'anchor': return <AnchorPage />
      case 'files': return <FilesPage />
      default: return <ImagePage />
    }
  }

  return (
    <>
      <Layout activeTab={activeTab} onTabChange={setActiveTab} onOpenSettings={() => setShowSettings(true)}>
        {renderPage()}
      </Layout>
      <Toast />
      <Settings show={showSettings} onClose={() => setShowSettings(false)} />
    </>
  )
}