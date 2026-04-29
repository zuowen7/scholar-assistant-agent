import { API_BASE } from '../utils/api'
import { insertImage } from './useEditorState'

export type VisionAnalysisType = 'general' | 'chart' | 'table' | 'formula'

export interface VisionAnalysisResponse {
  text?: string
  chart_type?: string
  chart_description?: string
  table_data?: string[][]
  key_findings?: string[]
  raw_description?: string
}

export interface ImageUploadResponse {
  path: string
  filename: string
  url: string
  size: number
}

export function useEditorVision() {
  const API = API_BASE

  async function uploadImage(file: File): Promise<ImageUploadResponse | null> {
    const formData = new FormData()
    formData.append('file', file)
    const resp = await fetch(`${API}/api/upload/image`, { method: 'POST', body: formData })
    if (!resp.ok) return null
    return await resp.json() as ImageUploadResponse
  }

  async function analyzeVision(file: File, analysisType: VisionAnalysisType = 'general'): Promise<VisionAnalysisResponse | null> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('analysis_type', analysisType)
    const resp = await fetch(`${API}/api/vision/analyze`, { method: 'POST', body: formData })
    if (!resp.ok) return null
    return await resp.json() as VisionAnalysisResponse
  }

  async function ocrImage(file: File): Promise<VisionAnalysisResponse | null> {
    const formData = new FormData()
    formData.append('file', file)
    const resp = await fetch(`${API}/api/vision/ocr`, { method: 'POST', body: formData })
    if (!resp.ok) return null
    return await resp.json() as VisionAnalysisResponse
  }

  async function analyzeChart(file: File): Promise<VisionAnalysisResponse | null> {
    const formData = new FormData()
    formData.append('file', file)
    const resp = await fetch(`${API}/api/vision/chart`, { method: 'POST', body: formData })
    if (!resp.ok) return null
    return await resp.json() as VisionAnalysisResponse
  }

  async function extractTableFromImage(file: File): Promise<VisionAnalysisResponse | null> {
    const formData = new FormData()
    formData.append('file', file)
    const resp = await fetch(`${API}/api/vision/table`, { method: 'POST', body: formData })
    if (!resp.ok) return null
    return await resp.json() as VisionAnalysisResponse
  }

  async function insertImageFile(file: File): Promise<ImageUploadResponse | null> {
    const data = await uploadImage(file)
    if (!data) return null
    insertImage(data.url || data.path, data.filename || file.name)
    return data
  }

  return { uploadImage, insertImageFile, analyzeVision, ocrImage, analyzeChart, extractTableFromImage }
}
